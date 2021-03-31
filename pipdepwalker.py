# a pip dependency walker (recursively)
# cyyang
# 2021/3/26

# x -- list .whl/.tar.gz deps from pypi online (recursively)

# 1. list .whl/.tar.gz deps from local .whl/.tar.gz (recursively)
# 2. using pip download to get dependencies
# 3. get requires of each pkg untill reaching depth limit
# 4. generate requires tree, and pip install script

# then you can use pip install in a offline env

# others like pipreqs, pipdeptree

# pip-download is good, but not recursively
# and download overhead is high
# ref https://github.com/youngquan/pip-download

# pypi index
# https://mirrors.aliyun.com/pypi/simple/
# https://pypi.tuna.tsinghua.edu.cn/simple/



import os
import re
import json
import tarfile
import shutil
import tempfile
from threading import Thread, Lock
import subprocess, shlex
from collections import OrderedDict

from argparse import ArgumentParser
import pkginfo

from threadpool import ThreadPool



class DepWalker():
    ''' pip dependency walker '''
    def __init__(self, pypi_src='https://pypi.org/simple/', depth_limit=-1, platform='manylinux1_x86_64', pv='cp38', thread_num=10):
        '''
            pypi_src: pypi index,
            depth_limit: 0, 1, 2, ..., -1 for deepest
            platform: suffix of whl packages except 'none-any', like 'win_amd64', 'manylinux1_x86_64'
            pv: implementation and python version, like 'cp38', 'cp37'
            thread_num: thread num
        '''
        # super(DepWalker).__init__(self, name='watcher')

        self.pypi_src = pypi_src
        self.depth_limit = depth_limit
        self.platform = platform
        self.implementation = pv[:2]
        self.python_version = pv[-2:]

        self.dest_dir = '.'

        # reqs may diff, but pkg_names are same
        # reqs: vine<5.0.0a1,>=1.1.3 vine==1.3.0
        # pkg_name: vine-1.3.0-py2.py3-none-any.whl
        self.reqs = {}      # req : pkg_name, amqp<2.7,>=2.6.0 : amqp-2.6.1-py2.py3-none-any.whl
        self.pkgs = {}      # pkg_name : actual stored seq, amqp-2.6.1-py2.py3-none-any.whl : 2_0
        self.seqs = {}      # str(seq) : (req, pkg_name), 2_0 : (amqp<2.7,>=2.6.0, amqp-2.6.1-py2.py3-none-any.whl)

        self.pool = ThreadPool(self.walker, thread_num, 2, 0)
        self.print_lock = Lock()
        self.lock = Lock()


    def get_reqs(self, pkg_name):
        '''
            get (basic) requirements from pkg, .whl/.tar.gz
        '''
        if pkg_name.endswith('.whl'):
            metadata = pkginfo.get_metadata(pkg_name)
            reqs = [i.replace('(', '').replace(')', '').replace(' ', '') for i in metadata.requires_dist if ';' not in i]
            return reqs
        elif pkg_name.endswith('.tar.gz'):
            with tarfile.open(pkg_name, 'r') as tf:
                reqs_files = [i for i in tf.getnames() if 'requires.txt' in i]
                if len(reqs_files) > 0:
                    reqs_file = reqs_files[0]
                else:
                    # has no requires.txt
                    return []
                buf = tf.extractfile(reqs_file)
                # buf.seek(0)
                reqs = buf.read().decode()
                reqs = [i for i in reqs.partition('\n\n')[0].strip('\n').split('\n')]
                return reqs
        else:
            print(f'get reqs err, {pkg_name}')
            return []


    def download_pkg(self, pkg, dest_dir):
        '''
            download pkg like: python-dateutil>=2.7.3, numpy>=1.16.5 ...
            download to a temp folder to avoid mulit-thread conflict
            in windows, if len(dest_dir + pkg_name) > 260, may raise err
        '''
        cmd = f'pip download {pkg} --no-deps --platform {self.platform} --implementation {self.implementation} --python-version {self.python_version} -i {self.pypi_src} -d {dest_dir} --progress-bar off'
        retcode = subprocess.run(shlex.split(cmd), capture_output=True)
        # retcode.check_returncode()      # raise CalledProcessError

        if retcode.stderr != b'':
            print(retcode.stderr.decode())
            return '', retcode.stderr.decode()
        elif retcode.stdout != b'':
            out = re.findall(r'.*\\(.+?)\r\nSuccessfully downloaded', retcode.stdout.decode())
            if len(out) > 0:
                return out[0], ''
            else:
                print(f'{pkg} name not found')
                return '', retcode.stdout.decode()


    def walker(self, pkg_name, seq=[], upper={}, root=False):
        '''
            pkg_name: pkg file name, .whl/.tar.gz
        '''
        if root: self.reqs, self.pkgs, self.seqs = {}, {}, {}

        print(f'walk {pkg_name}, depth {seq}')

        reqs = self.get_reqs(pkg_name)
        if len(reqs) == 0:
            print(f'{pkg_name} has no dependencies')
            return

        with self.lock:
            upper.update({r:OrderedDict() for r in reqs})

        pkg_name_version = re.findall(r'(^[\w-]+-[\d\.]+\d+)', pkg_name.rpartition('/')[2])[0]

        content = f'{pkg_name_version} has [{len(reqs)}] dependencies: {", ".join(reqs)}'
        print(seq, content)

        for i, r in enumerate(reqs):
            seq_r = seq + [i]
            seq_r_str = '_'.join([f'{s:d}' for s in seq_r])
            if r not in self.reqs:
                print(f'downloading {r}')

                temp_folder = tempfile.mkdtemp(prefix='pipdepwalker_').replace('\\', '/')
                pkg_name_r, out_err = self.download_pkg(r, temp_folder)
                if len(pkg_name_r) == 0:
                    content = f'err downloading {r} required by {pkg_name_version}'
                    print(seq_r, content, out_err)
                    with self.lock:
                        with open(f'{self.dest_dir}/errors.txt', 'a', encoding='utf-8') as f:
                            f.write(f'{seq_r}, {content}\n{out_err}\n\n')
                    continue

                print(f'{r} successfully downloaded')

                with self.lock:
                    self.reqs[r] = pkg_name_r

                if pkg_name_r not in self.pkgs:
                    with self.lock:
                        self.pkgs[pkg_name_r] = seq_r_str

                    pkg_path = f'{self.dest_dir}/{seq_r_str}/{pkg_name_r}'

                    if not os.path.exists(pkg_path):
                        os.makedirs(f'{self.dest_dir}/{seq_r_str}', exist_ok=True)
                        shutil.move(f'{temp_folder}/{pkg_name_r}', pkg_path)
                    else:
                        os.remove(f'{temp_folder}/{pkg_name_r}')

                else:
                    os.remove(f'{temp_folder}/{pkg_name_r}')
                    print(f'{r} required by {pkg_name_version} was already downloaded, {pkg_name_r}')

                os.rmdir(temp_folder)

            else:
                print(f'{r} required by {pkg_name_version} was already downloaded')

            with self.lock:
                self.seqs[seq_r_str] = (r, self.reqs[r])

            # actual store path
            # pkg_name_r = self.reqs[r]
            # seq_r_str = self.pkgs[pkg_name_r]
            # pkg_path = f'{self.dest_dir}/{seq_r_str}/{pkg_name_r}'

            # walk through the whole graph, DFS & BFS, both are ok
            # (DFS) recursively walk
            # self.walker(pkg_path, seq=seq_r, upper=upper[r])
            # self.pool.add_task_nowait(pkg_path, seq=seq_r, upper=upper[r])


        if self.depth_limit >= 0:
            if len(seq) >= self.depth_limit: return

        # (BFS) recursively walk
        for i, r in enumerate(reqs):
            seq_r = seq + [i]   # use this!

            # check if circular dependency
            pkg_name_chain = [self.seqs.get('_'.join([f'{s:d}' for s in seq_r[:j+1]]))[1] for j in range(len(seq_r))]
            if len(set(pkg_name_chain)) < len(pkg_name_chain):
                content = f'circular dependency found: {", ".join(pkg_name_chain)}'
                print(content)
                with self.lock:
                    with open(f'{self.dest_dir}/errors.txt', 'a', encoding='utf-8') as f:
                        f.write(f'{seq_r}, {content}\n\n')
                continue

            # actual store path
            pkg_name_r = self.reqs[r]
            seq_r_str = self.pkgs[pkg_name_r]
            pkg_path = f'{self.dest_dir}/{seq_r_str}/{pkg_name_r}'
            # seq_r = [int(s) for s in seq_r_str.split('_')]  # WRONG! this is actual store seq!

            # self.walker(pkg_path, seq=seq_r, upper=upper[r])
            self.pool.add_task_nowait(pkg_path, seq=seq_r, upper=upper[r])

        content = f'{pkg_name_version} [{len(reqs)}] dependencies are all downloaded'
        print(seq, content)


    def adjust_pkg_sequence(self):
        '''
            DFS sorting
        '''
        seqs_keys = [[int(i) for i in k.split('_')] for k in self.seqs.keys()]
        max_depth = len(max(seqs_keys, key=lambda x: len(x)))

        # extend seq by 'inf' to max_depth
        for i in seqs_keys:
            i.extend([float('inf')] * (max_depth - len(i)))

        seqs_keys_sorted = [[i for i in seqs if i != float('inf')] for seqs in sorted(seqs_keys)]

        paths = []
        pkgs_processed = set()
        for seqs in seqs_keys_sorted:
            _, pkg_name = self.seqs.get('_'.join([f'{i:d}' for i in seqs]))

            if pkg_name in pkgs_processed:
                continue

            pkg_name_version_chain = [re.findall(r'(^[\w-]+-[\d\.]+\d+)', self.seqs.get('_'.join([f'{s:d}' for s in seqs[:i+1]]))[1])[0] for i in range(len(seqs))]

            path = f'{self.dest_dir}/{"_deps/".join(pkg_name_version_chain[:-1])}_deps' if len(pkg_name_version_chain) > 1 else self.dest_dir
            os.makedirs(path, exist_ok=True)

            if os.path.exists(f'{self.dest_dir}/{self.pkgs.get(pkg_name)}/{pkg_name}'):
                shutil.move(f'{self.dest_dir}/{self.pkgs.get(pkg_name)}/{pkg_name}', f'{path}/{pkg_name}')
                os.rmdir(f'{self.dest_dir}/{self.pkgs.get(pkg_name)}')

                paths.append(f'{path}/{pkg_name}')
            else:
                print(f'err, {self.dest_dir}/{self.pkgs.get(pkg_name)}/{pkg_name} not exists')
                paths.append(f'# err {path}/{pkg_name}')

            pkgs_processed.add(pkg_name)

        return paths

    
    def gen_pip_install_scripts(self, pkg_name, paths, reqs_dict):
        content = f'# to install {pkg_name}, max_depth={self.depth_limit}...\n' + \
                    'pip install \\\n' + \
                    ' \\\n'.join(paths) + \
                    f' \\\n{pkg_name}'

        print('\n')
        print(content)
        with open(f'{self.dest_dir}/{pkg_name}_pip.sh', 'w', encoding='utf-8') as f:
            f.write(content)
        with open(f'{self.dest_dir}/{pkg_name}_deps.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(reqs_dict, indent=2))


    def walk(self, pkg_name):
        if pkg_name.endswith('.whl') or pkg_name.endswith('.tar.gz'):
            if not os.path.exists(pkg_name):
                print(f'err {pkg_name} not exists')
                return -1

        else:
            pkg_name_r, out_err = self.download_pkg(pkg_name, '.')
            if len(pkg_name_r) == 0:
                content = f'err downloading {pkg_name}'
                print(content, out_err)
                with open(f'{self.dest_dir}/errors.txt', 'a', encoding='utf-8') as f:
                    f.write(f'{content}\n{out_err}\n\n')
                return -1
            print(f'{pkg_name} successfully downloaded')
            pkg_name = f'./{pkg_name_r}'

        cwd = pkg_name.replace("\\", "/").rpartition("/")[0]
        if cwd == '':
            cwd = '.'
            pkg_name = f'./{pkg_name}'
        pkg_name_version = re.findall(r'(^[\w-]+-[\d\.]+\d+)', pkg_name.rpartition('/')[2])[0]
        self.dest_dir = f'{cwd}/{pkg_name_version}_deps'
        reqs_dict = OrderedDict()

        self.walker(pkg_name, upper=reqs_dict, root=True)

        self.pool.wait_completion()

        paths = self.adjust_pkg_sequence()

        self.gen_pip_install_scripts(pkg_name, paths, reqs_dict)
        return 0



def run():
    parser = ArgumentParser()
    parser.add_argument('pkg_name', help='pkg name, accept .whl/.tar.gz, or requirement, like pkg_name==1.0.0')
    parser.add_argument('-i', '--index_url', default='https://pypi.org/simple/', help='base URL of the Python Package Index (default https://pypi.org/simple)')
    parser.add_argument('-p', '--platform', default='manylinux1_x86_64', help="suffix of whl packages except 'none-any', like 'win_amd64', 'manylinux1_x86_64' (default 'manylinux1_x86_64')")
    parser.add_argument('-v', '--python_version', default='cp38', help="implementation and python version, like 'cp38', 'cp37' (default 'cp38')")
    parser.add_argument('-n', '--thread_num', default=10, type=int, help='parallel download thread num (default 10)')
    parser.add_argument('-d', '--depth_limit', default=-1, type=int, help='0, 1, 2, ..., -1 for deepest (default -1)')

    args = parser.parse_args()

    # python pipdepwalker.py ./celery-4.4.7-py2.py3-none-any.whl -i https://mirrors.aliyun.com/pypi/simple/ -p manylinux1_x86_64 -v cp37 -n 5 -d -1

    # print((args.pkg_name, args.index_url, args.platform, args.python_version, args.thread_num, args.depth_limit))
    # return
 
    dw = DepWalker(pypi_src=args.index_url, depth_limit=args.depth_limit, platform=args.platform, pv=args.python_version)

    dw.walk(args.pkg_name)

    # test
    # dw = DepWalker(pypi_src='https://mirrors.aliyun.com/pypi/simple/', depth_limit=-1, platform='manylinux1_x86_64', pv='cp37')

    # dw.walk('./pandas-1.1.5-cp37-cp37m-manylinux1_x86_64.whl')

    # dw.walk('./pandas-1.2.3.tar.gz')

    # dw.walk('./celery-4.4.7-py2.py3-none-any.whl')

    # dw.walk('./slackclient-2.5.0-py2.py3-none-any.whl')

    # dw.walk('./apache-superset-1.0.1.tar.gz')



if __name__ == '__main__':

    run()



# metadata = pkginfo.get_metadata('./pandas-1.1.5-cp37-cp37m-manylinux1_x86_64.whl')
# metadata.requires_dist
# ['python-dateutil (>=2.7.3)',
#  'pytz (>=2017.2)',
#  'numpy (>=1.15.4)',
#  "pytest (>=4.0.2) ; extra == 'test'",
#  "pytest-xdist ; extra == 'test'",
#  "hypothesis (>=3.58) ; extra == 'test'"]


# buf = tf.extractfile(r'pandas-1.2.3/pandas.egg-info/requires.txt')
# # buf.seek(0)
# buf.read().decode()

# python-dateutil>=2.7.3\npytz>=2017.3\nnumpy>=1.16.5\n\n[test]\npytest>=5.0.1\npytest-xdist\nhypothesis>=3.58\n

# python-dateutil>=2.7.3
# pytz>=2017.3
# numpy>=1.16.5

# [test]
# pytest>=5.0.1
# pytest-xdist
# hypothesis>=3.58


# pip download python-dateutil>=2.7.3 --no-deps --platform manylinux1_x86_64 --implementation cp --python-version 37 -i https://mirrors.aliyun.com/pypi/simple/ -d ./deps


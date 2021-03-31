# pipdepwalker
a pip dependency walker (recursively, multi-threaded)

1. list .whl/.tar.gz deps from local .whl/.tar.gz (recursively, multi-threaded)
2. using pip download to get dependencies
3. get requires of each pkg untill reaching depth limit
4. generate requires tree, and pip install script

then you can use pip install in a offline env

others like pipreqs, pipdeptree, pip-download

# usage
```
usage: pipdepwalker.py [-h] [-i INDEX_URL] [-p PLATFORM] [-v PYTHON_VERSION] [-n THREAD_NUM] [-d DEPTH_LIMIT] pkg_name

positional arguments:
  pkg_name              pkg name, accept .whl/.tar.gz, or requirement, like pkg_name==1.0.0

optional arguments:
  -h, --help            show this help message and exit
  -i INDEX_URL, --index_url INDEX_URL
                        base URL of the Python Package Index (default https://pypi.org/simple)
  -p PLATFORM, --platform PLATFORM
                        suffix of whl packages except 'none-any', like 'win_amd64', 'manylinux1_x86_64' (default
                        'manylinux1_x86_64')
  -v PYTHON_VERSION, --python_version PYTHON_VERSION
                        implementation and python version, like 'cp38', 'cp37' (default 'cp38')
  -n THREAD_NUM, --thread_num THREAD_NUM
                        parallel download thread num (default 10)
  -d DEPTH_LIMIT, --depth_limit DEPTH_LIMIT
                        0, 1, 2, ..., -1 for deepest (default -1)
```

# output
a folder contains all dependencies, a shell script with 'pip install', a json contains dependencies tree, and errors.txt if error occurs

# example
```python pipdepwalker.py ./example/celery-4.4.7-py2.py3-none-any.whl -i https://mirrors.aliyun.com/pypi/simple/ -p manylinux1_x86_64 -v cp37 -t 5 -d -1```

should generate:

folder 'celery-4.4.7_deps' contains all dependencies,
```
│  billiard-3.6.3.0-py3-none-any.whl
│  kombu-4.6.11-py2.py3-none-any.whl
│  pytz-2021.1-py2.py3-none-any.whl
│
└─kombu-4.6.11_deps
    │  amqp-2.6.1-py2.py3-none-any.whl
    │
    └─amqp-2.6.1_deps
            vine-1.3.0-py2.py3-none-any.whl
```

file celery-4.4.7-py2.py3-none-any.whl_pip.sh
```
# to install ./example/celery-4.4.7-py2.py3-none-any.whl, max_depth=-1...
pip install \
./example/celery-4.4.7_deps/pytz-2021.1-py2.py3-none-any.whl \
./example/celery-4.4.7_deps/billiard-3.6.3.0-py3-none-any.whl \
./example/celery-4.4.7_deps/kombu-4.6.11_deps/amqp-2.6.1_deps/vine-1.3.0-py2.py3-none-any.whl \
./example/celery-4.4.7_deps/kombu-4.6.11_deps/amqp-2.6.1-py2.py3-none-any.whl \
./example/celery-4.4.7_deps/kombu-4.6.11-py2.py3-none-any.whl \
./example/celery-4.4.7-py2.py3-none-any.whl
```

file celery-4.4.7-py2.py3-none-any.whl_deps.json
```
{
  "pytz>dev": {},
  "billiard<4.0,>=3.6.3.0": {},
  "kombu<4.7,>=4.6.10": {
    "amqp<2.7,>=2.6.0": {
      "vine<5.0.0a1,>=1.1.3": {}
    }
  },
  "vine==1.3.0": {}
}
```

# screenshots

![Screenshot 1](https://github.com/ycysuk/pipdepwalker/blob/main/previews/1.PNG)

![Screenshot 2](https://github.com/ycysuk/pipdepwalker/blob/main/previews/2.PNG)

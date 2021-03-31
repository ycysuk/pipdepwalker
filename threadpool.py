# thread pool

from threading import Thread, Lock
from queue import Queue

class Worker(Thread):
    """Thread executing tasks from a given tasks queue"""
    def __init__(self, func, tasks, retrycnt=2):
        Thread.__init__(self)
        self.func = func
        self.tasks = tasks
        self.retrycnt = retrycnt
        self.running = 0
        self.daemon = True
        self.start()

    def run(self):
        while True:
            args, kargs = self.tasks.get()
            self.running = 1
            for _ in range(self.retrycnt):
                try:
                    self.func(*args, **kargs)
                    break
                except Exception as e:
                    try:
                        print(e, *args, **kargs)
                    except:
                        print(e)
                    continue
                # finally:
                    # self.tasks.task_done()
            self.tasks.task_done()
            self.running = 0



class ThreadPool:
    """Pool of threads consuming tasks from a queue"""
    def __init__(self, func, num_threads, retrycnt=2, qsize=None):
        if qsize != None:
            self.tasks = Queue(qsize)
        else:
            self.tasks = Queue(num_threads)
        self.workers = []
        for _ in range(num_threads):
            self.workers.append(Worker(func, self.tasks, retrycnt))

    def add_task(self, *args, **kargs):
        """Add a task to the queue"""
        self.tasks.put((args, kargs))

    def add_task_nowait(self, *args, **kargs):
        """Add a task to the queue"""
        try:
            self.tasks.put_nowait((args, kargs))
        except Exception as e:
            print(e)

    def wait_completion(self):
        """Wait for completion of all the tasks in the queue"""
        self.tasks.join()

    def tasks_in_pool(self):
        return self.tasks.qsize() + sum([w.running for w in self.workers])


def run():
    # test
    import time

    def func(x):
        print(x)
        time.sleep(1)

    print('test\n')
    pool = ThreadPool(func, 2, 3, 0)
    for i in range(10):
        pool.add_task_nowait(i*i)

    while pool.tasks_in_pool() > 0:
        print(f'{pool.tasks_in_pool()} tasks in pool')
        time.sleep(1.5)
    pool.wait_completion()


if __name__ == '__main__':

    run()

bind = '0.0.0.0:8080'
#bind = 'unix:/tmp/gunicorn.sock'
workers = 2
keepalive = 60
worker_class = "gunicorn.workers.gtornado.TornadoWorker"
#accesslog = '-'
errorlog = '-'

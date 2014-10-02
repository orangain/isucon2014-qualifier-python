bind = '0.0.0.0:8080'
#bind = 'unix:/tmp/gunicorn.sock'
workers = 10
keepalive = 60
worker_class = "meinheld.gmeinheld.MeinheldWorker"
#accesslog = '-'
#errorlog = '-'

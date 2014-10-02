from werkzeug.contrib.profiler import ProfilerMiddleware, MergeStream
from app import app

app.config['PROFILE'] = True
app.wsgi_app = ProfilerMiddleware(app.wsgi_app, profile_dir='/home/isucon/continuous-profiler/output/pstats')
#app.run(debug = True)

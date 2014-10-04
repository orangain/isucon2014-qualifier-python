#from werkzeug.contrib.profiler import ProfilerMiddleware, MergeStream
from middlewares import ProfilerMiddleware
from app import app

#app.config['PROFILE'] = True
app = ProfilerMiddleware(app,  profile_dir='/home/isucon/continuous-profiler/output/pstats')
#app.run(debug = True)

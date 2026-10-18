"""Server-side validation for newly created SmartEye collections."""
def validator(required, properties):
    return {'$jsonSchema':{'bsonType':'object','required':['_id',*required],
                          'properties':{'_id':{'bsonType':['int','long']},**properties}}}


TEXT={'bsonType':'string'}
NUMBER={'bsonType':['int','long','double','decimal']}
INTEGER={'bsonType':['int','long']}
BOOL={'bsonType':'bool'}
SCHEMAS={
    'users':validator(['email','name','password','role','active','created_at'],{
        'email':TEXT,'name':TEXT,'password':TEXT,'role':{'enum':['user','analyst','admin']},'active':BOOL,'auth_version':INTEGER,'created_at':TEXT}),
    'segments':validator(['name','start_node','end_node','distance_km','geometry','active','is_demo'],{
        'name':TEXT,'start_node':TEXT,'end_node':TEXT,'distance_km':{**NUMBER,'minimum':.05},'geometry':{'bsonType':'array','minItems':2},'active':BOOL,'is_demo':BOOL}),
    'cameras':validator(['name','segment_id','capacity','roi','low_threshold','high_threshold','active'],{
        'name':TEXT,'segment_id':INTEGER,'capacity':{**INTEGER,'minimum':1},'roi':{'bsonType':'array','minItems':4,'maxItems':4},
        'low_threshold':{**NUMBER,'minimum':0,'maximum':1},'high_threshold':{**NUMBER,'minimum':0,'maximum':1},'active':BOOL}),
    'observations':validator(['segment_id','user_id','density','score','observed_at','source'],{
        'segment_id':INTEGER,'user_id':INTEGER,'density':{'enum':['LOW','NORMAL','HIGH']},'score':{**NUMBER,'minimum':0,'maximum':1},'observed_at':TEXT,'source':TEXT}),
    'video_jobs':validator(['user_id','camera_id','filename','status','progress','camera_config'],{
        '_id':TEXT,'user_id':INTEGER,'camera_id':INTEGER,'filename':TEXT,
        'status':{'enum':['queued','processing','completed','failed','cancelled']},'progress':{**INTEGER,'minimum':0,'maximum':100},'camera_config':{'bsonType':'object'}}),
    'sessions':validator(['user_id','expires_at'],{'_id':TEXT,'user_id':INTEGER,'expires_at':TEXT,'expires_on':{'bsonType':'date'}}),
    'reset_tokens':validator(['user_id','expires_at'],{'_id':TEXT,'user_id':INTEGER,'expires_at':TEXT,'expires_on':{'bsonType':'date'}}),
    'favorites':validator(['user_id','name','request'],{'user_id':INTEGER,'name':TEXT,'request':{'bsonType':'object'}}),
    'alert_rules':validator(['user_id','segment_id','density','active'],{'user_id':INTEGER,'segment_id':INTEGER,'density':{'enum':['LOW','NORMAL','HIGH']},'active':BOOL}),
    'notifications':validator(['user_id','message','read'],{'user_id':INTEGER,'message':TEXT,'read':BOOL}),
    'audit':validator(['action','detail','created_at'],{'action':TEXT,'detail':TEXT,'created_at':TEXT}),
}

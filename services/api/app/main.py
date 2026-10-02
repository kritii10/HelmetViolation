import os, shutil
from pathlib import Path
from uuid import uuid4
import httpx
from fastapi import FastAPI,File,HTTPException,UploadFile,status,Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,UUID4
from .celery_client import celery_client
app=FastAPI(title='Traffic Violation Intelligence API',version='0.3.0');app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173'],allow_methods=['*'],allow_headers=['*']);app.mount('/storage',StaticFiles(directory='/app/storage'),name='storage')
SERVICE=os.getenv('VIOLATION_SERVICE_URL','http://violation-service:8002');UPLOADS=Path('/app/storage/uploads')
class Start(BaseModel): video_id:UUID4
@app.get('/health')
def health(): return {'service':'api-gateway','status':'ok'}
@app.post('/api/videos/upload',status_code=201)
async def upload(video:UploadFile=File(...)):
 if not (video.content_type or '').startswith('video/'): raise HTTPException(415,'Please upload a video file.')
 vid=str(uuid4());path=UPLOADS/f"{vid}{Path(video.filename or 'video.mp4').suffix or '.mp4'}";UPLOADS.mkdir(parents=True,exist_ok=True)
 with path.open('wb') as f: shutil.copyfileobj(video.file,f)
 try:
  async with httpx.AsyncClient() as c:r=await c.post(f'{SERVICE}/videos',json={'id':vid,'filename':video.filename or 'video.mp4','filepath':str(path)});r.raise_for_status()
 except httpx.HTTPError as e: path.unlink(missing_ok=True);raise HTTPException(503,'Database service unavailable') from e
 return {'id':vid,'filename':video.filename,'filepath':f'/storage/uploads/{path.name}'}
@app.post('/api/analysis/start',status_code=status.HTTP_202_ACCEPTED)
async def start(body:Start):
 jid=str(uuid4())
 async with httpx.AsyncClient() as c:
  r=await c.post(f'{SERVICE}/jobs',json={'id':jid,'video_id':str(body.video_id)})
  if r.status_code==404: raise HTTPException(404,'Video not found')
  r.raise_for_status();vs=(await c.get(f'{SERVICE}/videos')).json();v=next((x for x in vs if x['id']==str(body.video_id)),None)
 if not v: raise HTTPException(404,'Video not found')
 celery_client.send_task('video_processor.process_video',args=[jid,v['filepath'],str(body.video_id)],queue='video_processing');return {'job_id':jid,'status':'queued','progress':0}
async def get(path,request):
 async with httpx.AsyncClient() as c:r=await c.get(f'{SERVICE}{path}',params=dict(request.query_params));r.raise_for_status();return r
@app.get('/api/analysis/{job_id}')
async def analysis(job_id:str,request:Request): return (await get(f'/jobs/{job_id}',request)).json()
@app.get('/api/violations')
async def violations(request:Request): return (await get('/violations',request)).json()
@app.get('/api/violations/{item}')
async def violation(item:str,request:Request): return (await get(f'/violations/{item}',request)).json()
@app.get('/api/statistics')
async def statistics(request:Request): return (await get('/statistics',request)).json()
@app.get('/api/videos')
async def videos(request:Request): return (await get('/videos',request)).json()
@app.get('/api/reports/violations')
async def reports():
 async with httpx.AsyncClient() as c:r=await c.get(f'{SERVICE}/reports/violations');r.raise_for_status();return Response(r.content,media_type='text/csv',headers={'Content-Disposition':'attachment; filename=violations.csv'})

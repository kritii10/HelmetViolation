import csv, io, os
from typing import Literal
from uuid import UUID, uuid4
import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, UUID4
from psycopg.rows import dict_row

app=FastAPI(title="Helmet Violation Management Service",version="1.0.0"); DATABASE_URL=os.environ["DATABASE_URL"]
def connection(): return psycopg.connect(DATABASE_URL,row_factory=dict_row)
def data(row):
    for key,value in row.items():
        if isinstance(value,UUID): row[key]=str(value)
        elif hasattr(value,"isoformat"): row[key]=value.isoformat()
    return row
class VideoCreate(BaseModel): id:UUID4;filename:str=Field(min_length=1,max_length=255);filepath:str=Field(min_length=1)
class JobCreate(BaseModel): id:UUID4;video_id:UUID4
class JobUpdate(BaseModel): status:Literal['queued','processing','completed','failed'];progress:int=Field(ge=0,le=100);error_message:str|None=None
class EvidenceCreate(BaseModel): evidence_type:Literal['frame','annotated_video'];filepath:str;confidence:float|None=Field(default=None,ge=0,le=1)
class ViolationCreate(BaseModel): job_id:UUID4;confidence:float=Field(ge=0,le=1);timestamp:float=Field(ge=0);duration:float=Field(ge=0);supporting_frames:int=Field(ge=1);evidence:list[EvidenceCreate]
@app.get('/health')
def health():
    with connection() as conn,conn.cursor() as cur:cur.execute('SELECT 1')
    return {'service':'helmet-violation-management','status':'ok'}
@app.post('/videos',status_code=201)
def create_video(v:VideoCreate):
    with connection() as conn,conn.cursor() as cur:cur.execute('INSERT INTO videos (id,filename,filepath) VALUES (%s,%s,%s)',(v.id,v.filename,v.filepath))
    return {'id':str(v.id),'filename':v.filename}
@app.get('/videos')
def videos():
    with connection() as conn,conn.cursor() as cur:cur.execute('SELECT v.id,v.filename,v.filepath,v.duration,v.uploaded_at,COUNT(j.id) AS job_count FROM videos v LEFT JOIN analysis_jobs j ON j.video_id=v.id GROUP BY v.id ORDER BY v.uploaded_at DESC');return [data(x) for x in cur.fetchall()]
@app.patch('/videos/{video_id}/duration')
def duration(video_id:UUID4,value:float=Query(ge=0)):
    with connection() as conn,conn.cursor() as cur:cur.execute('UPDATE videos SET duration=%s WHERE id=%s RETURNING id',(value,video_id));row=cur.fetchone()
    if not row:raise HTTPException(404,'Video not found')
    return {'id':str(row['id']),'duration':value}
@app.post('/jobs',status_code=201)
def create_job(j:JobCreate):
    with connection() as conn,conn.cursor() as cur:
        cur.execute('SELECT 1 FROM videos WHERE id=%s',(j.video_id,))
        if not cur.fetchone():raise HTTPException(404,'Video not found')
        cur.execute("INSERT INTO analysis_jobs (id,video_id,status,progress) VALUES (%s,%s,'queued',0)",(j.id,j.video_id))
    return {'id':str(j.id),'status':'queued','progress':0}
@app.patch('/jobs/{job_id}')
def update_job(job_id:UUID4,u:JobUpdate):
    with connection() as conn,conn.cursor() as cur:cur.execute("UPDATE analysis_jobs SET status=%s,progress=%s,error_message=%s,started_at=CASE WHEN %s='processing' AND started_at IS NULL THEN NOW() ELSE started_at END,completed_at=CASE WHEN %s IN ('completed','failed') THEN NOW() ELSE completed_at END WHERE id=%s RETURNING id,status,progress",(u.status,u.progress,u.error_message,u.status,u.status,job_id));row=cur.fetchone()
    if not row:raise HTTPException(404,'Job not found')
    return data(row)
@app.get('/jobs/{job_id}')
def job(job_id:UUID4):
    with connection() as conn,conn.cursor() as cur:
        cur.execute('SELECT j.id,j.video_id,j.status,j.progress,j.error_message,j.created_at,j.started_at,j.completed_at,v.filename,v.filepath,v.duration FROM analysis_jobs j JOIN videos v ON v.id=j.video_id WHERE j.id=%s',(job_id,));row=cur.fetchone()
        if not row:raise HTTPException(404,'Job not found')
        cur.execute('SELECT id,confidence,timestamp,duration,supporting_frames,created_at FROM violations WHERE job_id=%s ORDER BY timestamp',(job_id,));violations=cur.fetchall()
    result=data(row);result['violations']=[data(x) for x in violations];return result
@app.post('/violations',status_code=201)
def violation(v:ViolationCreate):
    violation_id=uuid4()
    with connection() as conn,conn.cursor() as cur:
        cur.execute('INSERT INTO violations (id,job_id,confidence,timestamp,duration,supporting_frames) VALUES (%s,%s,%s,%s,%s,%s)',(violation_id,v.job_id,v.confidence,v.timestamp,v.duration,v.supporting_frames))
        for item in v.evidence:cur.execute('INSERT INTO evidence (id,violation_id,evidence_type,filepath,confidence) VALUES (%s,%s,%s,%s,%s)',(uuid4(),violation_id,item.evidence_type,item.filepath,item.confidence))
    return {'violation_id':str(violation_id)}
@app.get('/violations')
def violations():
    with connection() as conn,conn.cursor() as cur:cur.execute('SELECT id,job_id,confidence,timestamp,duration,supporting_frames,created_at FROM violations ORDER BY created_at DESC');return [data(x) for x in cur.fetchall()]
@app.get('/violations/{violation_id}')
def violation_detail(violation_id:UUID4):
    with connection() as conn,conn.cursor() as cur:
        cur.execute('SELECT id,job_id,confidence,timestamp,duration,supporting_frames,created_at FROM violations WHERE id=%s',(violation_id,));row=cur.fetchone()
        if not row:raise HTTPException(404,'Violation not found')
        cur.execute('SELECT id,evidence_type,filepath,confidence,created_at FROM evidence WHERE violation_id=%s ORDER BY created_at',(violation_id,));evidence=cur.fetchall()
    result=data(row);result['evidence']=[data(x) for x in evidence];return result
@app.get('/statistics')
def stats():
    with connection() as conn,conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS value FROM videos WHERE EXISTS (SELECT 1 FROM analysis_jobs j WHERE j.video_id=videos.id AND j.status='completed')");videos_analyzed=cur.fetchone()['value']
        cur.execute('SELECT COUNT(*) AS value FROM violations');total=cur.fetchone()['value']
        cur.execute("SELECT COUNT(*) FILTER (WHERE status IN ('queued','processing')) AS active,COUNT(*) FILTER (WHERE status='completed') AS completed FROM analysis_jobs");jobs=cur.fetchone()
    return {'videos_analyzed':videos_analyzed,'no_helmet_violations':total,'active_jobs':jobs['active'],'completed_jobs':jobs['completed']}
@app.get('/reports/violations')
def report():
    with connection() as conn,conn.cursor() as cur:cur.execute("SELECT v.id AS violation_id,v.confidence,v.timestamp,v.duration,v.supporting_frames,MAX(e.filepath) FILTER (WHERE e.evidence_type='frame') AS evidence_path FROM violations v LEFT JOIN evidence e ON e.violation_id=v.id GROUP BY v.id ORDER BY v.created_at DESC");rows=cur.fetchall()
    out=io.StringIO();fields=['violation_id','confidence','timestamp','duration','supporting_frames','evidence_path'];writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader();writer.writerows([data(x) for x in rows]);out.seek(0)
    return StreamingResponse(out,media_type='text/csv',headers={'Content-Disposition':'attachment; filename=no_helmet_violations.csv'})

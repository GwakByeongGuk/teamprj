import base64, io
from fastapi import FastAPI, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from matplotlib import pyplot as plt
from starlette.requests import Request
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse
from app.model import models, database
from fastapi import HTTPException
from datetime import datetime

app = FastAPI()

# Jinja2 템플릿 설정
templates = Jinja2Templates(directory="views/templates")

# 애플리케이션 시작 시 DB 테이블 생성
@app.on_event("startup")
def on_startup():
    database.init_db()

@app.get("/", response_class=HTMLResponse)
async def read_main(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/approve-entry")
async def approve_entry(log_id: int = Form(...), db: Session = Depends(database.get_db)):
    # 해당 입출입 기록을 조회
    log = db.query(models.EntryExitLog).filter(models.EntryExitLog.no == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")

    log.exit_time = datetime.utcnow()
    db.commit()
    db.refresh(log)

    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/admin-login")
async def admin_login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(database.get_db)):
    admin = db.query(models.Admin).filter(models.Admin.id == username).first()

    if admin and admin.passwd == password:
        return RedirectResponse(url="/admin-dashboard", status_code=303)

    return HTMLResponse(content="로그인 실패: 아이디 또는 비밀번호가 잘못되었습니다.", status_code=401)

@app.post("/approve-login")
async def admin_login(request: Request, username2: str = Form(...), password2: str = Form(...), db: Session = Depends(database.get_db)):
    admin = db.query(models.Admin).filter(models.Admin.id == username2).first()

    if admin and admin.passwd == password2:
        return RedirectResponse(url="/user-dashboard", status_code=303)

    return HTMLResponse(content="로그인 실패: 아이디 또는 비밀번호가 잘못되었습니다.", status_code=401)

@app.get("/visitor-register", response_class=HTMLResponse)
async def visitor_register_page(request: Request):
    return templates.TemplateResponse("visitor_register.html", {"request": request})

@app.post("/visitor-register")
async def visitor_register(
        name: str = Form(...),
        email: str = Form(...),
        phone: str = Form(...),
        ob: str = Form(...),
        aname: str = Form(...),
        job: str = Form(...),
        db: Session = Depends(database.get_db)
):
    new_visitor = models.User(
        name=name,
        email=email,
        phone=phone,
        ob=ob,
        aname=aname,
        job=job,
        status=models.Status.PENDING
    )
    db.add(new_visitor)
    db.commit()
    db.refresh(new_visitor)

    return RedirectResponse(url="/user-dashboard", status_code=303)
@app.get("/visitor-confirmation", response_class=HTMLResponse)
async def visitor_confirmation_page(request: Request):
    return templates.TemplateResponse("visitor_confirmation.html", {"request": request})

@app.get("/user-dashboard/{user_id}", response_class=HTMLResponse)
async def user_dashboard(user_id: int, request: Request, db: Session = Depends(database.get_db)):
    visitor = db.query(models.User).filter(models.User.uno == user_id).first()
    if not visitor:
        return HTMLResponse(content="신청 내역을 찾을 수 없습니다.", status_code=404)

    return templates.TemplateResponse("user_dashboard.html", {"request": request, "visitor": visitor})

@app.post("/admin-approve/{visitor_id}")
async def admin_approve(visitor_id: int, db: Session = Depends(database.get_db)):
    visitor = db.query(models.User).filter(models.User.uno == visitor_id).first()

    if not visitor:
        return {"error": "방문자를 찾을 수 없습니다."}

    if visitor.status == models.Status.APPROVED:
        return {"error": "이미 승인된 기록이 있습니다."}

    visitor.status = models.Status.APPROVED
    db.commit()

    # 방문자 출입 기록 추가
    new_log = models.EntryExitLog(
        name=visitor.name,
        createdAt=datetime.now(),
        entry_time=datetime.now()
    )
    db.add(new_log)
    db.commit()

    return RedirectResponse(url="/admin-dashboard", status_code=303)

@app.post("/admin-reject/{uno}")
async def admin_reject(uno: int, db: Session = Depends(database.get_db)):
    visitor = db.query(models.User).filter(models.User.uno == uno).first()
    if visitor:
        visitor.status = "REJECTED"  # 거절 상태로 업데이트
        db.commit()
    return RedirectResponse(url="/admin-dashboard", status_code=303)

# 관리자 대시보드
@app.get("/admin-dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(database.get_db)):
    pending_visitors = db.query(models.User).filter(models.User.status == "PENDING").all()
    return templates.TemplateResponse("admin_dashboard.html", {"request": request, "pending_visitors": pending_visitors})

@app.get("/user-dashboard", response_class=HTMLResponse)
async def user_dashboard(request: Request, db: Session = Depends(database.get_db)):
    # 모든 사용자 데이터를 조회
    visitors = db.query(models.User).all()

    return templates.TemplateResponse("user_dashboard.html", {"request": request, "visitors": visitors})

@app.get("/visitor-list", response_class=HTMLResponse)
async def visitor_list(request: Request, db: Session = Depends(database.get_db)):
    visitors = db.query(models.User).all()
    return templates.TemplateResponse("visitor_list.html", {"request": request, "visitors": visitors})

@app.get("/statistics", response_class=HTMLResponse)
async def statistics_page(request: Request, db: Session = Depends(database.get_db)):
    logs = db.query(models.EntryExitLog).all()

    # 총 방문자 수
    total_visitors = len(logs)

    # 평균 방문 시간 계산 (초 단위에서 분 단위로 변환)
    total_duration = 0
    count = 0
    for log in logs:
        if log.entry_time and log.exit_time:
            duration = (log.exit_time - log.entry_time).total_seconds() / 60  # 분으로 변환
            total_duration += duration
            count += 1
    avg_visit_duration = total_duration / count if count > 0 else 0

    # 요일별 방문자 수 계산
    weekday_visitors = [0] * 7  # 0: 월요일, 6: 일요일
    for log in logs:
        weekday_visitors[log.entry_time.weekday()] += 1

    # 시간대별 방문자 수 계산
    hour_visitors = [0] * 24
    for log in logs:
        hour_visitors[log.entry_time.hour] += 1

    # 요일별 방문자 수 그래프 생성
    weekdays = ['월', '화', '수', '목', '금', '토', '일']
    fig, ax = plt.subplots()
    ax.bar(weekdays, weekday_visitors)
    ax.set_title("요일별 방문자 수")
    weekday_graph = save_graph_to_base64(fig)

    # 시간대별 방문자 수 그래프 생성
    hours = list(range(24))
    fig, ax = plt.subplots()
    ax.bar(hours, hour_visitors)
    ax.set_title("시간대별 방문자 수")
    hour_graph = save_graph_to_base64(fig)

    return templates.TemplateResponse("statistics.html", {
        "request": request,
        "total_visitors": total_visitors,
        "avg_visit_duration": avg_visit_duration,
        "weekday_graph": weekday_graph,
        "hour_graph": hour_graph
    })


def save_graph_to_base64(fig):
    img = io.BytesIO()
    fig.savefig(img, format='png')
    img.seek(0)
    graph_url = base64.b64encode(img.getvalue()).decode()
    plt.close(fig)
    return f"data:image/png;base64,{graph_url}"

@app.post("/exit/{visitor_id}")
async def log_exit(visitor_id: int, db: Session = Depends(database.get_db)):
    visitor = db.query(models.User).filter(models.User.uno == visitor_id).first()
    if not visitor:
        return {"error": "방문자를 찾을 수 없습니다."}

    log = db.query(models.EntryExitLog).filter(models.EntryExitLog.name == visitor.name).order_by(models.EntryExitLog.no.desc()).first()

    if not log:
        return {"error": "방문 기록을 찾을 수 없습니다."}

    if log.exit_time:
        return {"error": "이미 퇴입된 기록입니다."}

    log.exit_time = datetime.now()
    db.commit()

    visitor.status = models.Status.EXIT
    db.commit()

    return JSONResponse(content={"success": True, "message": "퇴입 완료!"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


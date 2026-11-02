
# ============================================================
# ① [02→04 수정] 필요한 라이브러리 가져오기
# ============================================================
# APIRouter       : URL과 처리 함수 연결
# Depends         : DB 세션 등의 의존성 주입
# Form            : HTML 입력값 받기
# HTTPException   : 404 등의 HTTP 오류 발생
# Request         : 브라우저 요청 정보
# HTMLResponse    : HTML 응답
# RedirectResponse: 다른 URL로 이동
# Jinja2Templates : HTML 템플릿 출력
#
# [04 신규]
# select     : DB 데이터 조회 SQL 구성
# Session    : DB 세션 타입
# get_db     : db.py에서 DB 세션 가져오기
# TextItem   : models.py에서 테이블 모델 가져오기
# analyze_text: services.py의 AI 감정분석 함수
#
# [02에서 제거]
# get_classifier, normalize_prediction
# → 이제 services.py에서 호출하므로
#   router.py에서 직접 가져오지 않습니다.

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import TextItem
from .services import analyze_text


# ============================================================
# ② [02 유지] 라우터와 HTML 템플릿 설정
# ============================================================
# router    : API 경로를 등록할 객체
# templates : HTML 파일이 들어 있는 폴더

router = APIRouter()
templates = Jinja2Templates(directory="templates")


# ============================================================
# ③ [04 신규] 공통 HTML 출력 함수
# ============================================================
# 02에서는 TemplateResponse()를 여러 번 작성했습니다.
#
# 이제 render() 함수를 만들어 HTML 출력 코드를 줄입니다.
#
# request : 브라우저 요청 정보
# name    : 출력할 HTML 파일 이름
# **context : HTML에 전달할 데이터
#
# 예:
# render(request, "predict.html", text="안녕하세요")
#
# 실제 템플릿 경로:
# sentiment/predict.html

def render(request, name, **context):

    return templates.TemplateResponse(
        request=request,
        name="sentiment/" + name,
        context=context
    )


# ============================================================
# ④ [02→04 수정] 입력값 검사를 공통 함수로 분리
# ============================================================
# 02에서는 predict() 안에서 문장 길이를 검사했습니다.
#
# 04에서는 감정분석, 글 작성, 글 수정에
# 같은 검사가 필요하므로 checked()로 분리합니다.
#
# 정상 입력 : 정리된 문장 반환
# 잘못된 입력 : None 반환

def checked(text):

    # 입력 문장 앞뒤 공백 제거
    cleaned = text.strip()

    # 문장이 1~500자가 아니면 None 반환
    if not 1 <= len(cleaned) <= 500:
        return None

    # 정상적인 입력 문장 반환
    return cleaned


# ============================================================
# ⑤ [04 신규] 첫 화면 접속 시 목록으로 이동
# ============================================================
# 사용자가 / 주소로 접속하면 /items/로 이동합니다.
#
# 303 : 다른 URL로 이동하도록 안내하는 상태 코드

@router.get("/", include_in_schema=False)
def home():

    return RedirectResponse(
        "/items/",
        status_code=303
    )


# ============================================================
# ⑥ [02→04 수정] 기존 감정분석 입력 화면
# ============================================================
# 기존 GET /predict/ 기능은 그대로 유지합니다.
#
# 변경된 점:
# TemplateResponse() 대신 render() 함수 사용

@router.get(
    "/predict/",
    response_class=HTMLResponse,
    name="predict_page"
)
def predict_page(request: Request):

    return render(
        request,
        "predict.html",
        text="",
        result=None,
        error=None
    )


# ============================================================
# ⑦ [02→04 수정] 감정분석 POST 요청과 입력 검사
# ============================================================
# 사용자가 [분석하기] 버튼을 누르면 실행됩니다.
#
# 02 : predict() 내부에서 직접 문장 검사
# 04 : checked() 공통 함수를 사용
#
# 잘못된 입력은 HTTP 400 응답을 반환합니다.

@router.post(
    "/predict/",
    response_class=HTMLResponse,
    name="predict"
)
def predict(
    request: Request,
    text: str = Form(default="")
):

    # 공통 함수로 입력값 검사
    value = checked(text)

    # 정상 문장이 아니라면 오류 화면 출력
    if value is None:

        return templates.TemplateResponse(
            request=request,
            name="sentiment/predict.html",
            context={
                "text": text,
                "result": None,
                "error": "문장은 1~500자로 입력하세요."
            },
            status_code=400
        )


    # --------------------------------------------------------
    # ⑧ [02→04 수정] 서비스 함수를 통한 AI 감정분석
    # --------------------------------------------------------
    # 02:
    # get_classifier()로 모델을 가져온 후 직접 분석
    #
    # 04:
    # services.py의 analyze_text() 함수 호출
    #
    # analyze_text()는 label, score를 반환합니다.
    #
    # 주의:
    # /predict/는 기존처럼 분석 결과만 출력하며
    # SQLite에는 저장하지 않습니다.

    return render(
        request,
        "predict.html",
        text=value,
        result={
            "input": value,
            **analyze_text(value)
        },
        error=None
    )


# ============================================================
# ⑨ [04 신규] 저장된 감정분석 글 목록 조회 (READ)
# ============================================================
# GET /items/
#
# Depends(get_db) :
# db.py에서 DB 세션을 받아옵니다.
#
# select(TextItem) :
# text_items 테이블의 데이터를 조회합니다.
#
# order_by(TextItem.id.desc()) :
# id가 큰 글부터 정렬합니다.
#
# .all() :
# 조회된 모든 결과를 가져옵니다.

@router.get(
    "/items/",
    response_class=HTMLResponse,
    name="item_list"
)
def item_list(
    request: Request,
    db: Session = Depends(get_db)
):

    # DB에 저장된 전체 글 조회
    items = db.scalars(
        select(TextItem).order_by(TextItem.id.desc())
    ).all()

    # 조회 결과를 목록 HTML에 전달
    return render(
        request,
        "textitem_list.html",
        items=items
    )


# ============================================================
# ⑩ [04 신규] 새 글 작성 화면 열기 (CREATE 화면)
# ============================================================
# GET /new/
#
# 사용자가 새 글을 작성할 수 있도록 HTML 폼을 보여줍니다.
# 아직 DB에 저장하거나 AI 분석을 실행하지 않습니다.

@router.get(
    "/new/",
    response_class=HTMLResponse,
    name="item_create_page"
)
def item_create_page(request: Request):

    return render(
        request,
        "textitem_form.html",
        item=None,
        text="",
        error=None
    )


# ============================================================
# ⑪ [04 신규] 새 글 저장 요청 및 입력값 검사
# ============================================================
# POST /new/
#
# 사용자가 [저장] 버튼을 누르면 실행됩니다.
#
# text : 입력 문장
# db   : SQLite 작업에 사용할 DB 세션
#
# 먼저 checked()로 입력 문장을 검사합니다.

@router.post("/new/", name="item_create")
def item_create(
    request: Request,
    text: str = Form(default=""),
    db: Session = Depends(get_db)
):

    # 입력 문장 검사
    value = checked(text)

    # 잘못된 문장이라면 저장하지 않고 오류 출력
    if value is None:

        return templates.TemplateResponse(
            request=request,
            name="sentiment/textitem_form.html",
            context={
                "item": None,
                "text": text,
                "error": "문장은 1~500자로 입력하세요."
            },
            status_code=400
        )


    # --------------------------------------------------------
    # ⑫ [04 신규] AI 분석 → SQLite 저장 → 상세 페이지 이동
    # --------------------------------------------------------
    # 1. analyze_text()로 AI 감정분석 실행
    # 2. TextItem 객체 생성
    # 3. db.add()로 저장할 객체 등록
    # 4. db.commit()으로 저장 확정
    # 5. db.refresh()로 저장된 정보 다시 읽기
    # 6. 상세 페이지로 이동
    #
    # 중요:
    # 현재 04는 동기식 처리입니다.
    # AI 분석이 완료된 후 DB에 저장하고 응답합니다.

    # AI 감정분석 실행
    result = analyze_text(value)

    # models.py에 정의한 TextItem 모델 객체 생성
    item = TextItem(
        text=value,
        label=result["label"],
        score=result["score"]
    )

    # DB 세션에 새 객체 등록
    db.add(item)

    # DB 저장 확정
    db.commit()

    # 저장된 데이터 다시 읽기
    db.refresh(item)

    # 저장된 글의 상세 페이지로 이동
    return RedirectResponse(
        request.url_for(
            "item_detail",
            item_id=item.id
        ),
        status_code=303
    )


# ============================================================
# ⑬ [04 신규] 저장된 글 상세 조회 (READ)
# ============================================================
# GET /items/{item_id}/
#
# item_id : 조회하려는 글의 고유번호(PK)
#
# db.get(TextItem, item_id) :
# 해당 id를 가진 글을 조회합니다.
#
# 데이터가 없다면 HTTP 404 오류를 발생시킵니다.

@router.get(
    "/items/{item_id}/",
    response_class=HTMLResponse,
    name="item_detail"
)
def item_detail(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db)
):

    # 기본키(id)로 데이터 조회
    item = db.get(TextItem, item_id)

    # 해당 글이 없으면 404 오류
    if item is None:
        raise HTTPException(
            status_code=404,
            detail="해당 글이 없습니다."
        )

    # 조회 결과를 상세 페이지에 전달
    return render(
        request,
        "textitem_detail.html",
        item=item
    )


# ============================================================
# ⑭ [04 신규] 기존 글 수정 화면 열기 (UPDATE 화면)
# ============================================================
# GET /items/{item_id}/edit/
#
# 수정할 글을 DB에서 조회합니다.
# 기존 입력 문장을 HTML 폼에 표시합니다.
#
# 이 단계에서는 실제 수정 작업을 하지 않습니다.

@router.get(
    "/items/{item_id}/edit/",
    response_class=HTMLResponse,
    name="item_update_page"
)
def item_update_page(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db)
):

    # 수정할 글 조회
    item = db.get(TextItem, item_id)

    # 글이 없으면 404
    if item is None:
        raise HTTPException(status_code=404)

    # 기존 내용을 수정 폼에 전달
    return render(
        request,
        "textitem_form.html",
        item=item,
        text=item.text,
        error=None
    )


# ============================================================
# ⑮ [04 신규] 기존 글 수정 요청 및 입력값 검사
# ============================================================
# POST /items/{item_id}/edit/
#
# 수정할 데이터를 먼저 조회하고,
# 새로운 문장이 정상 입력인지 검사합니다.

@router.post(
    "/items/{item_id}/edit/",
    name="item_update"
)
def item_update(
    request: Request,
    item_id: int,
    text: str = Form(default=""),
    db: Session = Depends(get_db)
):

    # 수정할 기존 데이터 조회
    item = db.get(TextItem, item_id)

    # 데이터가 존재하지 않으면 404
    if item is None:
        raise HTTPException(status_code=404)

    # 수정한 문장 검사
    value = checked(text)

    # 잘못된 입력이면 수정하지 않고 오류 출력
    if value is None:

        return templates.TemplateResponse(
            request=request,
            name="sentiment/textitem_form.html",
            context={
                "item": item,
                "text": text,
                "error": "문장은 1~500자로 입력하세요."
            },
            status_code=400
        )


    # --------------------------------------------------------
    # ⑯ [04 신규] AI 재분석 → 데이터 수정 → DB 저장
    # --------------------------------------------------------
    # 수정한 문장을 AI 모델로 다시 분석합니다.
    #
    # 이후 TextItem의 값을 변경하고 commit()합니다.
    #
    # 수정 항목:
    # text  : 수정된 문장
    # label : 새 감정분석 결과
    # score : 새 감정분석 점수

    # AI 감정분석 다시 실행
    result = analyze_text(value)

    # ORM 객체의 컬럼값 수정
    item.text = value
    item.label = result["label"]
    item.score = result["score"]

    # DB 수정사항 확정
    db.commit()

    # 수정된 글 상세 페이지로 이동
    return RedirectResponse(
        request.url_for(
            "item_detail",
            item_id=item_id
        ),
        status_code=303
    )


# ============================================================
# ⑰ [04 신규] 글 삭제 확인 화면 열기 (DELETE 화면)
# ============================================================
# GET /items/{item_id}/delete/
#
# 삭제할 글을 조회하고
# 정말 삭제할지 확인하는 HTML 화면을 보여줍니다.
#
# 이 단계에서는 아직 삭제하지 않습니다.

@router.get(
    "/items/{item_id}/delete/",
    response_class=HTMLResponse,
    name="item_delete_page"
)
def item_delete_page(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db)
):

    # 삭제할 글 조회
    item = db.get(TextItem, item_id)

    # 존재하지 않으면 404
    if item is None:
        raise HTTPException(status_code=404)

    # 삭제 확인 화면 출력
    return render(
        request,
        "textitem_confirm_delete.html",
        item=item
    )


# ============================================================
# ⑱ [04 신규] 글 삭제 실행 (DELETE)
# ============================================================
# POST /items/{item_id}/delete/
#
# 사용자가 삭제 확인 버튼을 누르면 실행됩니다.
#
# 1. 삭제할 데이터 조회
# 2. db.delete()로 삭제 등록
# 3. db.commit()으로 삭제 확정
# 4. 글 목록 페이지로 이동

@router.post(
    "/items/{item_id}/delete/",
    name="item_delete"
)
def item_delete(
    item_id: int,
    db: Session = Depends(get_db)
):

    # 삭제할 글 조회
    item = db.get(TextItem, item_id)

    # 글이 없으면 404
    if item is None:
        raise HTTPException(status_code=404)

    # 해당 객체 삭제 등록
    db.delete(item)

    # DB 삭제 확정
    db.commit()

    # 목록 페이지로 이동
    return RedirectResponse(
        "/items/",
        status_code=303
    )
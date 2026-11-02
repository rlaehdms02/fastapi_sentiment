# FastAPI 감정분석 CRUD (02 → 04)

Hugging Face 감정분석 모델을 FastAPI 웹 서비스에 연결하고, 분석 결과를 SQLite에 저장해 **목록 · 상세 · 수정 · 삭제(CRUD)** 할 수 있게 만든 실습 프로젝트입니다.

```text
[02] 입력 → 모델 추론 → 화면 출력 (저장 X)
[04] 입력 → 모델 추론 → DB 저장 → 목록/상세/수정/삭제
[06] 입력 → DB 먼저 저장 → Celery가 나중에 분석 → DB 갱신 (비동기, 다음 단계)
```

- 환경: Windows + WSL2(Ubuntu 24.04), Python 3.12, VS Code, `uv`
- 모델: [`tabularisai/multilingual-sentiment-analysis`](https://huggingface.co/tabularisai/multilingual-sentiment-analysis)
- DB: SQLite (`sentiment.db`), ORM: SQLAlchemy 2.x

---

## 1. 폴더 구조

```text
fastapi_sentiment/
├── main.py                     # 앱 조립: DB 테이블 생성, CSS·라우터 연결, /health
├── sentiment.db                # 실행 시 생성되는 SQLite 파일 (데이터 저장 위치)
├── requirements.txt
├── sentiment/
│   ├── __init__.py             # sentiment 폴더를 파이썬 패키지로 표시
│   ├── hf_model.py             # Hugging Face 모델 로딩·재사용, 결과 정리
│   ├── services.py             # analyze_text(): 공통 분석 함수   (04 신규)
│   ├── db.py                   # engine, SessionLocal, Base, get_db (04 신규)
│   ├── models.py               # TextItem = text_items 테이블      (04 신규)
│   └── router.py               # URL ↔ 처리 함수 (CRUD)           (04 교체)
├── templates/
│   ├── base.html
│   └── sentiment/
│       ├── predict.html
│       ├── textitem_list.html            (04 신규)
│       ├── textitem_detail.html          (04 신규)
│       ├── textitem_form.html            (04 신규)
│       └── textitem_confirm_delete.html  (04 신규)
├── static/css/sentiment.css
└── tests/test_web.py
```

### `__init__.py`가 있는 이유
`sentiment` 폴더를 **패키지**로 만들어서 import할 수 있게 합니다. 내용은 비어 있어도 됩니다.

```python
from sentiment.router import router   # main.py (폴더 밖 → 안)
from .db import get_db                # router.py (같은 패키지 안, 점 = 같은 폴더)
```

---

## 2. 설치와 실행

```bash
cd ~/fastapi_sentiment
uv venv --python 3.12
source .venv/bin/activate
uv pip install "fastapi>=0.115,<1" "uvicorn[standard]" python-multipart jinja2 \
               "transformers>=4.55,<5" torch httpx pytest "sqlalchemy>=2,<3"
uv pip freeze > requirements.txt

python -m uvicorn main:app --reload
```

| 주소 | 화면 |
|---|---|
| `http://127.0.0.1:8000/` | `/items/`로 자동 이동 |
| `/items/` | 저장된 기록 목록 |
| `/new/` | 새 글 작성 → 저장하면 분석 후 상세로 이동 |
| `/items/{id}/` | 상세 (수정 · 삭제 · 목록 버튼) |
| `/predict/` | 즉시 분석 (저장 안 함, 02 기능) |
| `/health` | `{"status":"ok"}` |
| `/docs` | 자동 API 문서 |

자동 테스트:

```bash
python -m pytest -q
```

### 02 → 04 작업 순서
없는 파일을 먼저 import하지 않도록 이 순서로 만듭니다.

`sqlalchemy 설치` → `db.py` → `models.py` → `services.py` → `router.py` 교체 → 템플릿 4개 → `main.py` 교체 → (선택) `tests/test_web.py` 교체

---

## 3. 아키텍처 파이프라인

### 역할 분담

| 파일 | 역할 | 비유 |
|---|---|---|
| `main.py` | 앱 생성, 테이블 생성, CSS·라우터 연결 | 건물 입구 |
| `router.py` | URL 접수, 입력 검사, 응답 결정 | 접수 창구 |
| `services.py` | 분석 로직 한 곳에 모음 | 실무 담당자 |
| `hf_model.py` | 모델 로딩·재사용, 결과 형식 통일 | AI 비서 관리실 |
| `db.py` | DB 연결, 요청마다 세션 제공 | 창고 출입 관리 |
| `models.py` | 테이블 구조 정의 | 창고 선반 설계도 |
| `templates/` | 화면 모양 (Jinja2) | 출력 양식 |

### import 관계

```text
                    main.py
          ┌────────────┼──────────────┐
          ▼            ▼              ▼
     router.py       db.py        models.py
          │      (Base, engine)  (테이블 등록)
   ┌──────┼──────────────┐
   ▼      ▼              ▼
 db.py  models.py   services.py
(get_db)(TextItem)       │
          │              ▼
        db.py        hf_model.py
        (Base)           │
                         ▼
                transformers → Hugging Face Hub
```

`db.py`와 `hf_model.py`는 프로젝트 안의 다른 파일을 import하지 않는 **기초 부품**입니다.

### 요청 하나의 흐름 (`POST /new/`)

```text
[브라우저] 문장 입력 → [저장]
    │ POST /new/ (text=...)
    ▼
[Uvicorn] → [main.py] app → 라우터 찾기
    ▼
[router.py] item_create()
    ① checked() 1~500자 검사 ── 실패 → 400 + 폼 다시 표시
    ② Depends(get_db) ──────── db.py: 세션 생성
    ③ analyze_text() ────────── services.py → hf_model.py → {label, score}
    ④ TextItem(...) 생성 ────── models.py
    ⑤ db.add → db.commit → db.refresh ── sentiment.db에 INSERT
    ⑥ 303 Redirect → /items/{id}/
    ▼
[브라우저] GET /items/{id}/ → DB 조회 → textitem_detail.html
(요청이 끝나면 get_db의 with 블록이 세션을 닫음)
```

### 서버를 켤 때 실행 순서

```text
uvicorn main:app
 → main.py: sentiment.router import
     → db.py (engine, SessionLocal, Base)
     → models.py (TextItem이 Base에 등록)
     → services.py → hf_model.py (함수만 정의, 모델은 아직 로딩 X)
 → Base.metadata.create_all() → text_items 테이블 확인/생성
 → /static 연결 → include_router() → /health 등록 → 요청 대기
```

모델은 서버 시작이 아니라 **첫 분석 요청 때** 로딩됩니다(`@lru_cache`). 그래서 첫 저장만 느립니다.

---

## 4. 파일별 설명

### 4-1. `main.py` — 조립 파일

| 번호 | 코드 | 역할 |
|---|---|---|
| ① | `FastAPI`, `StaticFiles` | 앱·정적 파일 기능 준비 |
| ② | `from sentiment.router import router as sentiment_router` | URL 묶음 가져오기 (이때 db·models·services·hf_model도 로딩) |
| ③ | `from sentiment.db import Base, engine` | 테이블 생성에 필요 |
| ④ | `from sentiment import models` | `TextItem`을 `Base.metadata`에 등록 (지우면 `no such table`) |
| ⑤ | `app = FastAPI(title=...)` | 서버 본체. `uvicorn main:app`이 이 변수를 찾음 |
| ⑥ | `Base.metadata.create_all(bind=engine)` | **없는 테이블만** 생성 (컬럼 변경 X → 실무는 Alembic) |
| ⑦ | `app.mount("/static", ...)` | CSS 제공. `base.html`의 `url_for('static', ...)`과 연결 |
| ⑧ | `app.include_router(sentiment_router)` | router.py의 모든 URL을 앱에 연결 |
| ⑨⑩ | `@app.get("/health")` | 앱에 직접 만든 API. 서버 생존만 확인 (DB·모델 상태는 확인 X) |

### 4-2. `router.py` — 접수 창구

**공통 함수**

| 함수 | 역할 |
|---|---|
| `render(request, name, **context)` | `templates/sentiment/{name}`에 데이터를 넣어 200 응답 |
| `checked(text)` | 공백 제거 후 1~500자면 문장, 아니면 `None` |

400 응답이 필요한 곳은 `render()` 대신 `TemplateResponse(..., status_code=400)`를 직접 씁니다.

**경로 설계**

| CRUD | 메서드 | 경로 | 함수 (`name=`) | 처리 |
|---|---|---|---|---|
| – | GET | `/` | `home` | `/items/`로 303 |
| – | GET / POST | `/predict/` | `predict_page` / `predict` | 즉시 분석, **저장 X** |
| R | GET | `/items/` | `item_list` | `select(TextItem).order_by(id desc)` |
| C | GET | `/new/` | `item_create_page` | 빈 폼 (`item=None`) |
| C | POST | `/new/` | `item_create` | 검사 → 분석 → `add` → `commit` → `refresh` → 303 |
| R | GET | `/items/{item_id}/` | `item_detail` | `db.get()` → 없으면 404 |
| U | GET | `/items/{item_id}/edit/` | `item_update_page` | 기존 문장으로 폼 |
| U | POST | `/items/{item_id}/edit/` | `item_update` | 조회 → 검사 → **재분석** → 값 변경 → `commit` → 303 |
| D | GET | `/items/{item_id}/delete/` | `item_delete_page` | 확인 화면 (아직 삭제 X) |
| D | POST | `/items/{item_id}/delete/` | `item_delete` | `delete` → `commit` → `/items/`로 303 |

**함수 패턴**
- GET 화면: (조회 →) `render()` → 200
- POST 변경: (조회 → 404) → `checked()` → 400 / `analyze_text()` → `commit()` → **303**

**포인트**
- 수정에서 `db.add()`가 없는 이유: `db.get()`으로 가져온 객체는 세션이 이미 추적 중이라 값만 바꾸고 `commit()`하면 UPDATE가 됩니다.
- `db.refresh(item)`: DB가 자동으로 매긴 `id`를 다시 읽어 옵니다.
- `request.url_for("item_detail", item_id=...)`: 주소를 직접 쓰지 않고 **라우트 이름**으로 만듭니다.
- 삭제를 GET(확인) / POST(실행)로 나눈 이유: GET은 링크만 눌러도 실행되므로 실수 삭제를 막기 위해서입니다.
- 교재 설명과 달리 수정 시 문장이 같아도 **항상 재분석**합니다.

**라우터를 쓰는 이유**
1. `main.py`는 `include_router()`로 조립만 하고 코드가 짧아집니다.
2. 기능별로 파일을 나눌 수 있습니다 (`prefix="/anomaly"` 등으로 추가).
3. 역할이 분리되어 어디를 고칠지 명확합니다.
4. 한 줄로 기능 전체를 붙이거나 뺄 수 있습니다.
5. 모듈이 분리되어 테스트에서 `analyze_text`만 가짜로 바꿀 수 있습니다.

### 4-3. `services.py` — 공통 분석 함수

```text
analyze_text(text)
  → strip() → 빈 문장이면 ValueError
  → get_classifier()                         (hf_model.py)
  → classifier(text, truncation=True, max_length=512)
  → normalize_prediction(output)             (hf_model.py)
  → {"label": ..., "score": ...}
```

작성(Create)과 수정(Update)에서 같은 분석이 필요하므로 한 곳에 모았습니다. HTTP와 DB는 담당하지 않습니다.

### 4-4. `hf_model.py` — 모델 관리

| 번호 | 코드 | 역할 |
|---|---|---|
| ① | `lru_cache`, `pipeline` | 결과 기억 / Hugging Face 사용 도구 |
| ② | `MODEL_ID = "..."` | 모델 주소. **이 줄에서는 다운로드하지 않음** |
| ③ | `@lru_cache(maxsize=1)` | 첫 호출만 실제 실행, 이후 같은 모델 객체 반환 (같은 프로세스 안에서만) |
| ④ | `get_classifier()` | `pipeline("text-classification", model=MODEL_ID)` — 실제 다운로드·로딩 |
| ⑤~⑧ | `normalize_prediction()` | 리스트나 중첩 리스트 결과를 `{label: str, score: float}` 하나로 통일, 형식 오류면 `ValueError` |

`float()` 변환은 `numpy.float32` 같은 타입을 DB와 템플릿에서 문제없이 쓰기 위해서입니다.

### 4-5. `db.py` — DB 연결

| 부품 | 코드 | 만들어지는 때 | 역할 |
|---|---|---|---|
| URL | `sqlite:///./sentiment.db` | 1번 | **서버를 실행한 폴더**의 파일 |
| Engine | `create_engine(..., check_same_thread=False)` | 1번 | 연결 관리 + 커넥션 풀 |
| SessionLocal | `sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)` | 1번 | 세션 공장 |
| Base | `class Base(DeclarativeBase)` | 1번 | 테이블 모델의 부모 |
| Session | `SessionLocal()` → `db` | **요청마다** | 작업 공간(장바구니) |
| get_db | `with SessionLocal() as db: yield db` | 요청마다 | 세션 빌려주고 끝나면 닫기 |

- `check_same_thread=False`: FastAPI는 `def` 함수를 여러 스레드에서 실행하므로 SQLite의 스레드 검사를 끕니다 (SQLite 전용 옵션).
- `autoflush=False`: 조회 전에 변경 내용을 자동으로 DB에 보내지 않습니다.
- `expire_on_commit=False`: commit 후에도 객체 값이 유지됩니다.
- `yield`: 세션을 넘긴 뒤 멈춰 있다가, 요청이 끝나면 이어서 세션을 닫습니다. `return`으로는 닫는 시점을 잡을 수 없습니다.
- **commit은 자동이 아닙니다.** router에서 `db.commit()`을 호출해야 확정됩니다.

| 세션 동작 | 의미 |
|---|---|
| `db.add(item)` | 장바구니에 담기 |
| 속성 변경 | 세션이 변경을 추적 |
| `db.delete(item)` | 삭제 예약 |
| `db.commit()` | DB에 실제 INSERT/UPDATE/DELETE 확정 |
| `db.rollback()` | 취소 |

SQL을 직접 보고 싶으면 `create_engine(..., echo=True)`.

### 4-6. `models.py` — 테이블 설계도

| 파이썬 | DB |
|---|---|
| 클래스 `TextItem` | 테이블 `text_items` |
| 속성 | 컬럼 |
| 객체 하나 | 행 하나 |

| 컬럼 | 타입 | NULL | 기본값 | 채우는 곳 |
|---|---|---|---|---|
| `id` | Integer, PK | ✗ | 자동 번호 | SQLite |
| `text` | Text | ✗ | – | router (사용자 입력) |
| `label` | String(50) | ✗ | `""` | router (분석 결과) |
| `score` | Float | **○** | NULL | router (분석 결과) |
| `created_at` | DateTime(timezone=True) | ○ | 현재 UTC | SQLAlchemy 자동 |

- `Mapped[int]`: 파이썬 쪽 타입, `mapped_column(...)`: DB 쪽 설정 (SQLAlchemy 2.0 방식)
- `nullable=False`는 NULL만 막고 빈 문자열은 막지 않습니다. 길이 검사는 `checked()`가 합니다.
- `score`가 NULL 허용인 이유: 06 비동기에서 "미분석" 상태로 먼저 저장하기 위해서입니다.
- `default=lambda: datetime.now(...)`: `lambda`가 없으면 서버 시작 시각 하나가 모든 행에 들어갑니다.
- SQLite는 시간대를 저장하지 못합니다. UTC라서 한국 시간보다 9시간 이릅니다.
- **컬럼을 바꾸면** `create_all()`이 반영하지 않습니다. 실습에서는 `sentiment.db`를 지우고 다시 실행합니다.

---

## 5. 데이터 저장 위치

| 무엇 | 어디 |
|---|---|
| 분석 결과 (문장, label, score) | `~/fastapi_sentiment/sentiment.db` → `text_items` 테이블 |
| Hugging Face 모델 파일 | `~/.cache/huggingface/hub/` |

실제로 저장하는 코드는 `router.py`의 `commit()`입니다 (`/new/`, `/edit/`, `/delete/`). `/predict/`는 저장하지 않습니다.

확인 방법:

```bash
ls -lh sentiment.db
python -c "import sqlite3; c=sqlite3.connect('sentiment.db'); [print(r) for r in c.execute('select * from text_items')]"
```

또는 DBeaver → SQLite → `sentiment.db` → `text_items`.

주의:
- 다른 폴더에서 서버를 켜면 그 폴더에 빈 DB가 새로 생깁니다.
- `pytest`도 같은 `sentiment.db`를 사용합니다 (테스트 글을 저장했다가 삭제).
- 초기화: 서버 종료 → `rm sentiment.db` → 재실행.

---

## 6. Hugging Face 모델을 가져오는 방식

모델 **파일을 내 PC로 다운로드해서 내 PC(GPU)에서 실행**합니다. 문장을 Hugging Face 서버로 보내는 방식이 아닙니다.

```text
pipeline(model="tabularisai/multilingual-sentiment-analysis")
  → huggingface.co 저장소에서 config.json, model.safetensors, tokenizer 파일 다운로드
  → ~/.cache/huggingface/hub/ 저장 (다음부터 재사용)
  → 메모리/GPU 로딩 (Device set to use cuda:0)
  → 추론은 로컬에서 실행
```

`pipeline` 내부: 토크나이저(문장 → 숫자) → 모델(감정별 점수) → 후처리(최고 점수 + 라벨 이름).

| 코드 시점 | 다운로드 |
|---|---|
| `MODEL_ID = ...` | ✗ |
| 서버 시작 | ✗ |
| 첫 분석 요청 (`get_classifier()`) | ✅ |
| 이후 요청 | ✗ (`lru_cache`) |

단독 테스트(`model_test.py`):

```python
from transformers import pipeline
classifier = pipeline("text-classification", model="tabularisai/multilingual-sentiment-analysis")
print(classifier("오늘 정말 기분이 좋아요"))
# [{'label': 'Positive', 'score': 0.83...}]
```

- **학습이 아니라 추론**입니다. 입력 문장은 학습 데이터가 아닙니다.
- `score`는 모델의 확신 정도이지 정답 확률이 아닙니다.
- 이 코드를 라우터 안에 그대로 넣으면 요청마다 모델을 다시 로딩하므로 `hf_model.py`로 분리했습니다.

---

## 7. HTTP 상태 코드

| 코드 | 의미 | 이 프로젝트에서 |
|---|---|---|
| **200** OK | 성공 | 화면 정상 표시 |
| **303** See Other | 처리 끝, GET으로 이동 | 저장·수정·삭제 후 이동, `/` → `/items/` |
| **307** Temporary Redirect | 같은 방식으로 다시 요청 | `/items` → `/items/` 슬래시 자동 보정 |
| **400** Bad Request | 잘못된 입력 | 빈 문장, 500자 초과 (직접 지정) |
| **404** Not Found | 없음 | 없는 주소, 없는 글 번호 |
| 405 Method Not Allowed | 방식 불일치 | GET만 있는 곳에 POST |
| **422** Unprocessable Entity | 형식 오류 (FastAPI 자동) | `/items/abc/` |
| **500** Internal Server Error | 서버 코드 예외 | 테이블 없음, 모델 로딩 실패 → **서버 터미널 Traceback 확인** |

**PRG 패턴 (Post → Redirect → Get):** POST 후 303으로 GET 페이지에 보내서 새로고침해도 중복 저장되지 않게 합니다.

---

## 8. CRUD

| 글자 | 의미 | URL | SQL | SQLAlchemy |
|---|---|---|---|---|
| C | Create | `POST /new/` | INSERT | `db.add()` + `commit()` |
| R | Read | `GET /items/`, `/items/{id}/` | SELECT | `select()`, `db.get()` |
| U | Update | `POST /items/{id}/edit/` | UPDATE | 속성 변경 + `commit()` |
| D | Delete | `POST /items/{id}/delete/` | DELETE | `db.delete()` + `commit()` |

HTML `<form>`은 GET/POST만 보낼 수 있어서 수정·삭제도 POST를 씁니다. JSON API라면 보통 PUT/PATCH/DELETE를 씁니다.

---

## 9. 동기 vs 비동기

| | 04 동기 | 06 비동기 (Redis + Celery) |
|---|---|---|
| 응답 시점 | 분석이 **끝난 뒤** | 저장 **직후** |
| 사용자 대기 | 분석 시간만큼 | 거의 없음 |
| 결과 | 바로 보임 | 처음엔 "미분석", 나중에 갱신 |
| 구성 | FastAPI + DB | + Redis(작업 대기열) + Celery Worker(분석) |
| 적합 | 빠른 작업, 실습 | 느린 AI 추론, 대량 처리, 이미지·영상 |

`async def`는 같은 프로세스 안에서 **기다리는 작업**(네트워크, 파일)에 적합합니다. AI 추론처럼 **계산이 무거운 작업**에는 맞지 않아서 라우터는 일반 `def`로 두고, 무거운 분석은 06에서 Celery Worker(별도 프로세스)로 넘깁니다.

---

## 10. 자동 테스트 (`tests/test_web.py`)

실제 모델 대신 `fake_analyze()`로 `router.analyze_text`를 교체합니다 (monkeypatch). 다운로드 없이 빠르고 항상 같은 결과로 검증할 수 있습니다.

| 테스트 | 확인 |
|---|---|
| `test_health` | `/health` → `{"status":"ok"}` |
| `test_crud` | `/predict/` 200 → 빈 입력 400 → 저장 303 → 상세·목록 Positive → 수정 303 → Negative → 삭제 303 → 404 |
| `test_predict` | `/predict/` 회귀 테스트 (CRUD 추가 후에도 동작) |

`follow_redirects=False`: 303을 따라가지 않고 그대로 확인하기 위해 사용합니다.

---

## 11. 자주 나는 오류

| 오류 | 원인 | 해결 |
|---|---|---|
| `ModuleNotFoundError: sqlalchemy` | 설치 안 됨 / 다른 가상환경 | `source .venv/bin/activate` → `uv pip install "sqlalchemy>=2,<3"` (안 되면 `python -m pip install ...`) |
| `ImportError: cannot import name 'analyze_text'` | `services.py` 없음 | 작업 순서대로 파일 생성 |
| `TemplateNotFound` | 템플릿 위치 오류 | `templates/sentiment/` 안에 있는지 확인 |
| `no such table: text_items` | `main.py`에 `from sentiment import models` 누락 | 추가 후 재시작 |
| `no such column` | 모델 컬럼 변경 후 기존 DB 사용 | `sentiment.db` 삭제 후 재실행 |
| `NoMatchFound` | `url_for` 이름과 라우터 `name=` 불일치 | 이름 확인 |
| `GET / 404` | 02 상태 (04에서 해결) | 04 router.py 적용 |
| `WatchFiles detected changes` | `--reload` 자동 재시작 | 정상 |
| 첫 저장이 느림 | 첫 모델 로딩 | 정상 |

---

## 12. 한계와 확장

- 모델 오류를 router가 잡지 않아 500이 됩니다 → `try/except`로 폼에 오류 표시 가능
- 로그인·권한·CSRF 보호가 없습니다 (로컬 실습용)
- 테스트가 실제 DB를 사용합니다 → 실무는 테스트 DB 분리
- 스키마 변경은 Alembic 사용 권장
- DB 교체는 `db.py`의 `DATABASE_URL`만 수정 (PostgreSQL이면 `check_same_thread` 제거)

### 7일차 이상검출에 적용하기

같은 구조에 부품만 바꿉니다.

| 감정분석 (04) | 이상검출 |
|---|---|
| `hf_model.py`: `get_classifier()` + `lru_cache` | `create_backbone()` (ResNet18) + `lru_cache` |
| `normalize_prediction()` → `{label, score}` | Anomaly Score + Threshold → `{label: Normal/Anomaly, score}` |
| `services.py`: `analyze_text(text)` | `inspect_image(path)` |
| `TextItem` (text, label, score) | `InspectionItem` (image_path, label, score, threshold, heatmap_path) |
| `Form(text)` | `UploadFile` (이미지 업로드) |
| 고정 Rule 없음 | 서버 시작 시 `day07-anomaly-v1.0.json` 한 번 읽기 |

이미지와 히트맵 파일은 `media/` 같은 폴더에 저장하고, DB에는 **경로만** 저장합니다.

Hugging Face와 7일차의 연결 지점:
- **데이터**: `datasets.load_dataset()`으로 받아 `train/good`, `test/good`, `test/<결함>`, `ground_truth/` 폴더 구조로 저장 → 50~61번은 경로만 수정
- **모델**: `day07_anomaly_core.py`의 torchvision ResNet18을 Hugging Face Hub 모델로 교체 (분류 머리를 떼고 특징만 사용) → 공통 모듈만 수정
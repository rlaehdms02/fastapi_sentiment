
# ============================================================
# ① 날짜와 시간 처리 라이브러리 가져오기
# ============================================================
# datetime : 날짜와 시간을 표현하는 클래스
# timezone : 시간대 정보 설정
#
# timezone.utc : UTC(세계 표준시) 사용

from datetime import datetime, timezone


# ============================================================
# ② SQLAlchemy 데이터베이스 컬럼 타입 가져오기
# ============================================================
# Integer : 정수형 데이터
# Text    : 긴 문자열 데이터
# String  : 길이를 지정할 수 있는 문자열 데이터
# Float   : 실수형 데이터
# DateTime: 날짜 및 시간 데이터

from sqlalchemy import DateTime, Float, Integer, String, Text


# ============================================================
# ③ ORM 모델 작성에 필요한 기능 가져오기
# ============================================================
# Mapped        : Python 속성과 DB 컬럼의 연결 타입 표시
# mapped_column : DB 테이블 컬럼의 상세 설정

from sqlalchemy.orm import Mapped, mapped_column


# ============================================================
# ④ db.py에서 공통 부모 클래스 가져오기
# ============================================================
# Base는 db.py에서 만든 ORM 모델의 공통 부모 클래스입니다.
#
# TextItem이 Base를 상속하면
# SQLAlchemy에서 테이블 모델로 관리할 수 있습니다.

from .db import Base


# ============================================================
# ⑤ TextItem ORM 모델 및 테이블 이름 정의
# ============================================================
# TextItem : Python에서 사용하는 ORM 모델 클래스
#
# __tablename__ : 실제 데이터베이스 테이블 이름
#
# 이 클래스의 객체 하나는 DB의 데이터 한 행에 대응합니다.

class TextItem(Base):

    __tablename__ = "text_items"


    # --------------------------------------------------------
    # ⑥ id : 데이터 고유번호 (기본키)
    # --------------------------------------------------------
    # Integer          : 정수형
    # primary_key=True : 기본키(PK) 지정
    #
    # 각 감정분석 데이터를 구별하는 고유번호입니다.
    # SQLite에서는 정수 기본키로 자동 번호 생성이 가능합니다.

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )


    # --------------------------------------------------------
    # ⑦ text : 사용자가 입력한 문장
    # --------------------------------------------------------
    # Text           : 긴 문자열 저장
    # nullable=False : NULL 저장 불가
    #
    # 예: "오늘 정말 기분이 좋아요."
    #
    # 주의:
    # nullable=False는 NULL을 금지하는 설정입니다.
    # 빈 문자열까지 자동으로 검사하지는 않습니다.

    text: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )


    # --------------------------------------------------------
    # ⑧ label : AI 감정분석 결과
    # --------------------------------------------------------
    # String(50)      : 최대 50자로 설정한 문자열 타입
    # default=""      : 값을 지정하지 않으면 빈 문자열 사용
    # nullable=False  : NULL 저장 불가
    #
    # 예: Positive, Negative, Neutral

    label: Mapped[str] = mapped_column(
        String(50),
        default="",
        nullable=False
    )


    # --------------------------------------------------------
    # ⑨ score : AI 감정분석 점수
    # --------------------------------------------------------
    # Float         : 실수형 데이터
    # float | None  : 실수 또는 None 허용
    # nullable=True : DB에 NULL 저장 가능
    #
    # 예: 0.95
    #
    # 아직 AI 분석 결과가 없다면 NULL로 둘 수 있습니다.

    score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )


    # --------------------------------------------------------
    # ⑩ created_at : 데이터 생성 시각
    # --------------------------------------------------------
    # DateTime(timezone=True) : 시간대 정보를 고려한 타입 선언
    # default=lambda: ...    : 기본 생성 시각을 계산하는 함수
    # datetime.now(timezone.utc) : 현재 UTC 시각
    #
    # 새 데이터를 INSERT할 때 별도 값을 지정하지 않으면
    # 기본값으로 현재 UTC 시각을 사용합니다.

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
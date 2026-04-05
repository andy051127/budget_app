# ============================================================
# 심플 가계부 - Simple Budget Tracker
# Python 3 + customtkinter + SQLite3 + tkcalendar
# v3.0 - 달력 입력 / 수정 기능 / 헤더 정렬 / 글자 크기 / 당월 자동 조회
# ============================================================

import os                                         # 폴더/경로 처리
import sqlite3                                    # 내장 DB
from datetime import date, datetime               # 날짜 처리
from tkinter import ttk, messagebox               # 트리뷰, 팝업
import tkinter as tk                              # 기본 tkinter
import customtkinter as ctk                       # 모던 UI 위젯
from tkcalendar import Calendar                   # 달력 위젯 (pip install tkcalendar)

# ── 통계 기능 라이브러리 (pip install matplotlib pandas) ─────
try:
    import matplotlib
    matplotlib.use("TkAgg")                        # tkinter 백엔드 사용
    import matplotlib.ticker as mticker            # 금액 포맷 formatter
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # tk 임베딩
    from matplotlib.figure import Figure           # Figure 객체
    import pandas as pd                            # 데이터 집계
    HAS_STATS = True
except ImportError:
    HAS_STATS = False

# ── 전역 테마 설정 ──────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── 경로 설정 ───────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH  = os.path.join(DATA_DIR, "account_book.db")

# ── 구분별 분류 목록 (지출에 '담배' 추가) ───────────────────
CATEGORIES = {
    "수입": ["용돈", "월급", "부수입", "투자소득", "기타소득"],
    "저축": ["예/적금", "주식", "코인", "금/달러"],
    "지출": ["식비", "생활용품", "뷰티비용", "건강비용", "공부비용",
             "교통비", "문화비", "여행비", "통신비", "경조사비", "의료비", "담배", "기타"],
}

# ── 월 선택 목록 ────────────────────────────────────────────
MONTHS = ["전체"] + [f"{m}월" for m in range(1, 13)]

# ── 정렬 화살표 표시 ────────────────────────────────────────
ARROW = {True: " ↑", False: " ↓"}   # True=오름차순, False=내림차순

# ── 컬럼 표시 이름 ──────────────────────────────────────────
COL_LABELS = {
    "no": "No.", "date": "날짜", "type": "구분",
    "category": "분류", "amount": "금액", "note": "비고",
}

# ── _current_rows 튜플 내 인덱스 (정렬용) ───────────────────
# _current_rows 각 원소: (db_id, date, type, category, amount, note)
COL_IDX = {"date": 1, "type": 2, "category": 3, "amount": 4, "note": 5}

# ── 요약 카드 배경색 ─────────────────────────────────────────
COLOR_BALANCE = "#0d3d2b"
COLOR_INCOME  = "#0d2a3d"
COLOR_EXPENSE = "#3d0d0d"
COLOR_SAVING  = "#2a0d3d"


# ════════════════════════════════════════════════════════════
# 한글 폰트 설정 – matplotlib 그래프 내 한글 깨짐 방지
# ════════════════════════════════════════════════════════════
def _setup_korean_font():
    """윈도우 맑은 고딕 폰트를 matplotlib에 등록"""
    if not HAS_STATS:
        return
    import matplotlib.font_manager as fm
    import matplotlib.pyplot as plt

    candidates = [
        "C:/Windows/Fonts/malgun.ttf",    # 맑은 고딕
        "C:/Windows/Fonts/malgunbd.ttf",  # 맑은 고딕 Bold
    ]
    for fp in candidates:
        if os.path.exists(fp):
            fm.fontManager.addfont(fp)
            prop = fm.FontProperties(fname=fp)
            plt.rcParams["font.family"] = prop.get_name()
            break
    # 마이너스 기호 깨짐 방지
    plt.rcParams["axes.unicode_minus"] = False

if HAS_STATS:
    _setup_korean_font()


# ════════════════════════════════════════════════════════════
# DatePickerButton – tkcalendar.DateEntry 대체 위젯
#
# 문제: DateEntry 를 CTkScrollableFrame 안에 놓으면
#       달력 팝업이 grab_set() 시 스크롤 프레임 이벤트와 충돌 →
#       월/연도 이동 버튼이 먹히지 않음.
# 해결: Calendar 를 독립 Toplevel 에 띄우고 grab_set() 으로
#       팝업에만 이벤트를 집중 → 모든 달력 버튼 정상 동작.
# ════════════════════════════════════════════════════════════
class DatePickerButton(ctk.CTkFrame):
    """날짜 표시 엔트리 + 📅 버튼 조합의 커스텀 달력 위젯"""

    # 달력 팝업 다크 테마 색상
    _CAL_STYLE = dict(
        background           = "#1f538d",   # 헤더(월/연) 배경
        foreground           = "white",
        headersbackground    = "#12122a",   # 요일 헤더 배경
        headersforeground    = "#90b8f8",
        normalbackground     = "#1e1e2e",   # 날짜 셀 배경
        normalforeground     = "#e0e0e0",
        weekendbackground    = "#252535",
        weekendforeground    = "#f87171",
        othermonthbackground = "#141420",   # 이전/다음 달 날짜
        othermonthforeground = "#555555",
        selectbackground     = "#1f4e8c",   # 선택된 날짜 강조
        selectforeground     = "#ffffff",
        font                 = ("Malgun Gothic", 11),
        showweeknumbers      = False,
        borderwidth          = 0,
        date_pattern         = "yyyy-mm-dd",
    )

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent")
        self._popup = None  # 현재 열린 팝업 참조

        # 날짜 문자열 변수 (기본값: 오늘)
        self._var = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))

        # 날짜 텍스트 엔트리
        self._entry = ctk.CTkEntry(
            self, textvariable=self._var,
            placeholder_text="YYYY-MM-DD", height=36,
        )
        self._entry.pack(side="left", fill="x", expand=True)

        # 달력 열기 버튼
        ctk.CTkButton(
            self, text="📅", width=42, height=36,
            fg_color="#1f538d", hover_color="#2980b9",
            command=self._open_popup,
        ).pack(side="left", padx=(4, 0))

    # ── 팝업 열기 ────────────────────────────────────────────
    def _open_popup(self):
        # 이미 열려 있으면 닫기
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            return

        # 현재 엔트리 날짜 파싱 (실패 시 오늘)
        try:
            init = datetime.strptime(self._var.get(), "%Y-%m-%d").date()
        except ValueError:
            init = date.today()

        # ── Toplevel 생성 ─────────────────────────────────
        popup = tk.Toplevel(self.winfo_toplevel())
        popup.title("")
        popup.resizable(False, False)
        popup.configure(bg="#12122a")
        popup.overrideredirect(True)    # 타이틀바 없이 팝업처럼 보임
        self._popup = popup

        # ── Calendar 위젯 ─────────────────────────────────
        cal = Calendar(
            popup,
            year=init.year, month=init.month, day=init.day,
            selectmode="day",
            **self._CAL_STYLE,
        )
        cal.pack(padx=2, pady=(2, 0))

        # ── 하단 버튼 영역 ────────────────────────────────
        btn_bar = tk.Frame(popup, bg="#12122a")
        btn_bar.pack(fill="x", padx=6, pady=6)

        def _confirm():
            self._var.set(cal.get_date())   # "YYYY-MM-DD" 형식으로 저장
            popup.destroy()

        tk.Button(btn_bar, text="선택", command=_confirm,
                  bg="#1f538d", fg="white", activebackground="#2980b9",
                  activeforeground="white", relief="flat",
                  padx=18, pady=4, cursor="hand2",
                  font=("Malgun Gothic", 10, "bold")).pack(side="left", padx=(0, 4))

        tk.Button(btn_bar, text="닫기", command=popup.destroy,
                  bg="#3a3a3a", fg="white", activebackground="#555555",
                  activeforeground="white", relief="flat",
                  padx=12, pady=4, cursor="hand2",
                  font=("Malgun Gothic", 10)).pack(side="left")

        # ── 위치 계산: 버튼 아래, 화면 밖 넘침 보정 ─────
        popup.update_idletasks()
        bx = self.winfo_rootx()
        by = self.winfo_rooty() + self.winfo_height() + 2
        pw, ph = popup.winfo_reqwidth(), popup.winfo_reqheight()
        sw, sh = popup.winfo_screenwidth(), popup.winfo_screenheight()

        if bx + pw > sw:        # 오른쪽 벗어남
            bx = sw - pw - 6
        if by + ph > sh:        # 아래 벗어남 → 위쪽에 표시
            by = self.winfo_rooty() - ph - 2

        popup.geometry(f"+{bx}+{by}")
        popup.lift()
        popup.focus_force()

        # grab_set: 팝업에만 이벤트 집중 → 달력 내부 버튼 모두 정상 동작
        popup.grab_set()

    # ── DateEntry 와 동일한 외부 인터페이스 ─────────────────
    def get(self):
        """현재 날짜 문자열 반환 (YYYY-MM-DD)"""
        return self._var.get()

    def set_date(self, date_obj):
        """datetime.date 또는 'YYYY-MM-DD' 문자열로 날짜 설정"""
        if isinstance(date_obj, str):
            self._var.set(date_obj)
        else:
            self._var.set(date_obj.strftime("%Y-%m-%d"))


# ════════════════════════════════════════════════════════════
# Database 클래스 – SQLite CRUD 담당
# v3.0: update_transaction 추가
# ════════════════════════════════════════════════════════════
class Database:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)              # data 폴더 없으면 자동 생성
        self.conn = sqlite3.connect(DB_PATH)
        self._create_tables()

    # ── 테이블 생성 ─────────────────────────────────────────
    def _create_tables(self):
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                date       TEXT    NOT NULL,
                type       TEXT    NOT NULL,
                category   TEXT    NOT NULL,
                amount     INTEGER NOT NULL,
                note       TEXT    DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        self.conn.commit()

    # ── 거래 추가 ───────────────────────────────────────────
    def add_transaction(self, date_val, type_val, category, amount, note):
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO transactions (date, type, category, amount, note) VALUES (?,?,?,?,?)",
            (date_val, type_val, category, amount, note),
        )
        self.conn.commit()

    # ── 거래 수정 (UPDATE) ──────────────────────────────────
    # DB 고유 id(PK)를 기준으로 처리 – 화면의 순번(No.)과 무관
    def update_transaction(self, row_id, date_val, type_val, category, amount, note):
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE transactions
               SET date=?, type=?, category=?, amount=?, note=?
             WHERE id=?
        """, (date_val, type_val, category, amount, note, row_id))
        self.conn.commit()

    # ── 거래 삭제 ───────────────────────────────────────────
    def delete_transaction(self, row_id):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM transactions WHERE id=?", (row_id,))
        self.conn.commit()

    # ── 거래 조회 (year/month 필터 지원) ────────────────────
    # SQLite는 YEAR()/MONTH() 미지원 → strftime('%Y'/%m') 사용
    def get_all_transactions(self, year=None, month=None):
        cur = self.conn.cursor()
        base = "SELECT id, date, type, category, amount, note FROM transactions"
        if year and month:
            cur.execute(base + """ WHERE strftime('%Y', date)=?
                                     AND strftime('%m', date)=?
                                 ORDER BY date DESC, id DESC""",
                        (str(year), f"{month:02d}"))
        elif year:
            cur.execute(base + """ WHERE strftime('%Y', date)=?
                                 ORDER BY date DESC, id DESC""",
                        (str(year),))
        else:
            cur.execute(base + " ORDER BY date DESC, id DESC")
        return cur.fetchall()

    # ── 합계 조회 (year/month 필터 지원) ────────────────────
    def get_summary(self, year=None, month=None):
        cur = self.conn.cursor()

        def _sum(type_val):
            if year and month:
                cur.execute("""SELECT COALESCE(SUM(amount),0) FROM transactions
                               WHERE type=? AND strftime('%Y',date)=?
                                 AND strftime('%m',date)=?""",
                            (type_val, str(year), f"{month:02d}"))
            elif year:
                cur.execute("""SELECT COALESCE(SUM(amount),0) FROM transactions
                               WHERE type=? AND strftime('%Y',date)=?""",
                            (type_val, str(year)))
            else:
                cur.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type=?",
                            (type_val,))
            return cur.fetchone()[0]

        return _sum("수입"), _sum("지출"), _sum("저축")

    # ── 특정 월 이전까지의 누적 잔고 계산 ──────────────────
    # 월별 조회 시 해당 월의 이월금액을 자동 산출
    def get_balance_before(self, year, month):
        cur = self.conn.cursor()
        cutoff = f"{year:04d}-{month:02d}-01"   # YYYY-MM-01 미만 날짜를 조회
        cur.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='수입' AND date<?", (cutoff,))
        prev_income = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='지출' AND date<?", (cutoff,))
        prev_expense = cur.fetchone()[0]
        return int(self.get_setting("carryover", "0")) + prev_income - prev_expense

    # ── DB에 존재하는 연도 목록 ─────────────────────────────
    def get_distinct_years(self):
        cur = self.conn.cursor()
        cur.execute("SELECT DISTINCT strftime('%Y', date) FROM transactions ORDER BY 1 DESC")
        years = [int(r[0]) for r in cur.fetchall() if r[0]]
        if date.today().year not in years:
            years.insert(0, date.today().year)
        return years

    # ── 설정값 읽기 / 쓰기 ─────────────────────────────────
    def get_setting(self, key, default="0"):
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else default

    def set_setting(self, key, value):
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, str(value)))
        self.conn.commit()

    # ── 전체 기간 월별 합계 (통계 탭용) ────────────────────────
    # 반환: [(YYYY-MM, type, total), ...]
    def get_monthly_stats(self):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT strftime('%Y-%m', date) AS ym,
                   type,
                   SUM(amount)            AS total
            FROM   transactions
            GROUP  BY ym, type
            ORDER  BY ym
        """)
        return cur.fetchall()

    # ── 특정 월 분류별 합계 (통계 탭용) ─────────────────────
    # 반환: [(type, category, total), ...]
    def get_category_stats(self, year, month):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT type, category, SUM(amount) AS total
            FROM   transactions
            WHERE  strftime('%Y', date) = ?
              AND  strftime('%m', date) = ?
            GROUP  BY type, category
            ORDER  BY type, total DESC
        """, (str(year), f"{month:02d}"))
        return cur.fetchall()

    def close(self):
        self.conn.close()


# ════════════════════════════════════════════════════════════
# StatsFrame – 통계 탭 전체를 담당하는 프레임
#
# 레이아웃 (row):
#   0 – 컨트롤 바 (전체/월별 전환 + 월별 연도/월 선택)
#   1 – 요약 테이블 (ttk.Treeview, 고정 높이 195px)
#   2 – matplotlib 차트 (남은 공간 전부)
# ════════════════════════════════════════════════════════════
class StatsFrame(ctk.CTkFrame):
    def __init__(self, parent, db):
        super().__init__(parent, fg_color="transparent")
        self.db    = db
        self._mode = "overall"    # "overall" | "monthly"
        self._fig  = None
        self._canvas = None

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_control_bar()
        self._build_table_area()
        self._build_chart_area()

    # ────────────────────────────────────────────────────────
    # 컨트롤 바
    # ────────────────────────────────────────────────────────
    def _build_control_bar(self):
        bar = ctk.CTkFrame(self, corner_radius=10, fg_color="#1e1e2e")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        # 전체/월별 전환 버튼
        self._seg = ctk.CTkSegmentedButton(
            bar, values=["전체 통계", "월별 통계"],
            command=self._on_mode_change,
            height=34, font=ctk.CTkFont(size=12, weight="bold"),
        )
        self._seg.set("전체 통계")
        self._seg.pack(side="left", padx=12, pady=10)

        # 월별 전용 선택 영역 (초기 숨김, 월별 모드 시 pack)
        self._monthly_bar = ctk.CTkFrame(bar, fg_color="transparent")

        year_list = [str(y) for y in self.db.get_distinct_years()]
        self._stats_year_var  = ctk.StringVar(value=str(date.today().year))
        self._stats_month_var = ctk.StringVar(value=f"{date.today().month}월")

        ctk.CTkLabel(self._monthly_bar, text="연도",
                     font=ctk.CTkFont(size=12), text_color="#aaaaaa"
                     ).pack(side="left", padx=(0, 4))
        self._yr_combo = ctk.CTkComboBox(
            self._monthly_bar, values=year_list,
            variable=self._stats_year_var, width=88, height=30, state="readonly",
        )
        self._yr_combo.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(self._monthly_bar, text="월",
                     font=ctk.CTkFont(size=12), text_color="#aaaaaa"
                     ).pack(side="left", padx=(0, 4))
        ctk.CTkComboBox(
            self._monthly_bar, values=MONTHS[1:],   # "전체" 제외
            variable=self._stats_month_var, width=76, height=30, state="readonly",
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            self._monthly_bar, text="조회", width=64, height=30,
            fg_color="#1f538d", hover_color="#2980b9",
            command=self._show_monthly,
        ).pack(side="left")

        # 새로 고침 버튼
        ctk.CTkButton(
            bar, text="🔄", width=38, height=34,
            fg_color="#2b2b3a", hover_color="#3a3a4a",
            command=self.refresh,
        ).pack(side="right", padx=12, pady=10)

    # ────────────────────────────────────────────────────────
    # 요약 테이블 영역 (고정 높이)
    # ────────────────────────────────────────────────────────
    def _build_table_area(self):
        outer = ctk.CTkFrame(self, corner_radius=10, height=195)
        outer.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        outer.grid_propagate(False)
        outer.grid_rowconfigure(1, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        self._table_title = ctk.CTkLabel(
            outer, text="월별 요약",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self._table_title.grid(row=0, column=0, sticky="w", padx=14, pady=(8, 4))

        # 두 트리뷰가 같은 셀에 겹쳐 배치 → grid_remove 로 전환
        wrap = tk.Frame(outer, bg="#1e1e2e")
        wrap.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)

        # ── 전체 통계 트리뷰 ────────────────────────────────
        ov_cols = ("month", "income", "expense", "saving", "balance")
        self._ov_tree = ttk.Treeview(wrap, columns=ov_cols,
                                      show="headings", height=5, selectmode="none")
        ov_hdrs   = {"month": "월", "income": "수입", "expense": "지출",
                     "saving": "저축", "balance": "잔고(누적)"}
        ov_widths = {"month": 100, "income": 130, "expense": 130,
                     "saving": 110, "balance": 130}
        for c in ov_cols:
            self._ov_tree.heading(c, text=ov_hdrs[c])
            self._ov_tree.column(c, width=ov_widths[c], minwidth=60,
                                  anchor="center" if c == "month" else "e",
                                  stretch=(c == "balance"))

        self._ov_vsb = ttk.Scrollbar(wrap, orient="vertical",
                                      command=self._ov_tree.yview)
        self._ov_tree.configure(yscrollcommand=self._ov_vsb.set)
        self._ov_tree.grid(row=0, column=0, sticky="nsew")
        self._ov_vsb.grid(row=0, column=1, sticky="ns")
        self._ov_tree.tag_configure("stripe",    background="#252535")
        self._ov_tree.tag_configure("total_row", foreground="#90b8f8",
                                     background="#1a1a2e")

        # ── 월별 통계 트리뷰 ────────────────────────────────
        mo_cols = ("type", "category", "amount", "ratio")
        self._mo_tree = ttk.Treeview(wrap, columns=mo_cols,
                                      show="headings", height=5, selectmode="none")
        mo_hdrs   = {"type": "구분", "category": "분류",
                     "amount": "금액", "ratio": "비중(%)"}
        mo_widths = {"type": 80, "category": 160, "amount": 140, "ratio": 90}
        mo_anchors = {"type": "center", "category": "w", "amount": "e", "ratio": "center"}
        for c in mo_cols:
            self._mo_tree.heading(c, text=mo_hdrs[c])
            self._mo_tree.column(c, width=mo_widths[c], minwidth=60,
                                  anchor=mo_anchors[c], stretch=(c == "category"))

        self._mo_vsb = ttk.Scrollbar(wrap, orient="vertical",
                                      command=self._mo_tree.yview)
        self._mo_tree.configure(yscrollcommand=self._mo_vsb.set)
        self._mo_tree.grid(row=0, column=0, sticky="nsew")
        self._mo_vsb.grid(row=0, column=1, sticky="ns")
        self._mo_tree.tag_configure("income_row",  foreground="#4ade80")
        self._mo_tree.tag_configure("expense_row", foreground="#f87171")
        self._mo_tree.tag_configure("saving_row",  foreground="#60a5fa")
        self._mo_tree.tag_configure("stripe",      background="#252535")

        # 초기: 전체 통계 트리뷰만 표시
        self._mo_tree.grid_remove()
        self._mo_vsb.grid_remove()

    # ────────────────────────────────────────────────────────
    # matplotlib 차트 영역
    # ────────────────────────────────────────────────────────
    def _build_chart_area(self):
        outer = ctk.CTkFrame(self, corner_radius=10, fg_color="#1e1e2e")
        outer.grid(row=2, column=0, sticky="nsew")
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        self._fig    = Figure(facecolor="#1e1e2e")
        self._canvas = FigureCanvasTkAgg(self._fig, master=outer)
        self._canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew",
                                           padx=4, pady=4)

    # ════════════════════════════════════════════════════════
    # 이벤트 핸들러
    # ════════════════════════════════════════════════════════

    def _on_mode_change(self, value):
        if value == "전체 통계":
            self._mode = "overall"
            self._monthly_bar.pack_forget()           # 월별 선택 숨김
            self._mo_tree.grid_remove()
            self._mo_vsb.grid_remove()
            self._ov_tree.grid()
            self._ov_vsb.grid()
            self._table_title.configure(text="월별 요약")
            self._show_overall()
        else:
            self._mode = "monthly"
            self._monthly_bar.pack(side="left", padx=4, pady=10)  # 월별 선택 표시
            self._ov_tree.grid_remove()
            self._ov_vsb.grid_remove()
            self._mo_tree.grid()
            self._mo_vsb.grid()
            self._table_title.configure(text="분류별 내역")
            self._show_monthly()

    def refresh(self):
        """외부에서 데이터 변경 후 강제 갱신 호출"""
        if self._mode == "overall":
            self._show_overall()
        else:
            self._show_monthly()

    def refresh_years(self):
        """거래 추가/삭제 후 연도 콤보박스 목록 갱신"""
        year_list = [str(y) for y in self.db.get_distinct_years()]
        self._yr_combo.configure(values=year_list)

    # ════════════════════════════════════════════════════════
    # 데이터 로드 & 렌더링
    # ════════════════════════════════════════════════════════

    def _show_overall(self):
        rows = self.db.get_monthly_stats()
        if not rows:
            for r in self._ov_tree.get_children():
                self._ov_tree.delete(r)
            self._show_empty_chart("전체 거래 내역이 없습니다")
            return

        # DB 결과 → DataFrame → 피벗 (index=월, columns=구분)
        df = pd.DataFrame(rows, columns=["month", "type", "total"])
        df_pivot = df.pivot_table(index="month", columns="type",
                                  values="total", aggfunc="sum").fillna(0)
        for col in ["수입", "지출", "저축"]:          # 없는 컬럼 0으로 보장
            if col not in df_pivot.columns:
                df_pivot[col] = 0

        self._fill_overall_table(df_pivot)
        self._draw_line_chart(df_pivot)

    def _show_monthly(self):
        try:
            year  = int(self._stats_year_var.get())
            month = int(self._stats_month_var.get().replace("월", ""))
        except ValueError:
            return

        rows = self.db.get_category_stats(year, month)
        if not rows:
            for r in self._mo_tree.get_children():
                self._mo_tree.delete(r)
            self._show_empty_chart(f"{year}년 {month}월 데이터가 없습니다")
            return

        df = pd.DataFrame(rows, columns=["type", "category", "total"])
        self._fill_monthly_table(df)
        self._draw_bar_chart(df, year, month)

    # ── 전체 요약 테이블 채우기 ─────────────────────────────
    def _fill_overall_table(self, df_pivot):
        for r in self._ov_tree.get_children():
            self._ov_tree.delete(r)

        carryover = int(self.db.get_setting("carryover", "0"))
        running   = carryover
        t_inc = t_exp = t_sav = 0

        for i, (month, row) in enumerate(df_pivot.iterrows()):
            inc = int(row.get("수입", 0))
            exp = int(row.get("지출", 0))
            sav = int(row.get("저축", 0))
            running  = running + inc - exp
            t_inc += inc; t_exp += exp; t_sav += sav
            tags = ("stripe",) if i % 2 == 1 else ()
            self._ov_tree.insert("", "end",
                                  values=(month, f"{inc:,}", f"{exp:,}",
                                          f"{sav:,}", f"{running:,}"),
                                  tags=tags)

        # 합계 행
        self._ov_tree.insert("", "end",
                              values=("합  계", f"{t_inc:,}", f"{t_exp:,}",
                                      f"{t_sav:,}", "—"),
                              tags=("total_row",))

    # ── 월별 분류 테이블 채우기 ─────────────────────────────
    def _fill_monthly_table(self, df):
        for r in self._mo_tree.get_children():
            self._mo_tree.delete(r)

        exp_df = df[df["type"] == "지출"].sort_values("total", ascending=False)
        inc_df = df[df["type"] == "수입"].sort_values("total", ascending=False)
        sav_df = df[df["type"] == "저축"].sort_values("total", ascending=False)
        combined = pd.concat([exp_df, inc_df, sav_df])

        totals = {t: df[df["type"] == t]["total"].sum() for t in ["수입", "지출", "저축"]}

        for i, (_, row) in enumerate(combined.iterrows()):
            denom = totals.get(row["type"], 0)
            ratio = f"{row['total']/denom*100:.1f}%" if denom > 0 else "—"
            ctag  = {"수입": "income_row", "지출": "expense_row",
                     "저축": "saving_row"}.get(row["type"], "")
            tags  = (ctag, "stripe") if i % 2 == 1 else (ctag,)
            self._mo_tree.insert("", "end",
                                  values=(row["type"], row["category"],
                                          f"{int(row['total']):,} 원", ratio),
                                  tags=tags)

    # ════════════════════════════════════════════════════════
    # 차트 그리기
    # ════════════════════════════════════════════════════════

    # ── 선형 그래프 (전체 통계) ─────────────────────────────
    def _draw_line_chart(self, df_pivot):
        self._fig.clear()
        ax = self._fig.add_subplot(111, facecolor="#1e1e2e")

        months = list(df_pivot.index)
        x      = list(range(len(months)))

        # 수입/지출/저축 각각 다른 색상·마커로 표시
        SERIES = [("수입", "#4ade80", "o"), ("지출", "#f87171", "s"), ("저축", "#60a5fa", "^")]
        plotted = False
        for col, color, marker in SERIES:
            if col in df_pivot.columns and df_pivot[col].sum() > 0:
                ax.plot(x, df_pivot[col].tolist(),
                        color=color, marker=marker, label=col,
                        linewidth=2, markersize=5)
                plotted = True

        if not plotted:
            self._show_empty_chart("표시할 데이터가 없습니다")
            return

        ax.set_xticks(x)
        ax.set_xticklabels(months, rotation=40, ha="right",
                            color="#aaaaaa", fontsize=9)
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
        ax.tick_params(axis="y", colors="#aaaaaa", labelsize=9)
        ax.spines[:].set_color("#3a3a4a")
        ax.grid(axis="y", color="#3a3a4a", linestyle="--", alpha=0.5)
        ax.set_title("월별 수입 / 지출 / 저축 추이",
                      color="#e0e0e0", fontsize=12, pad=10)
        ax.set_ylabel("금액 (원)", color="#aaaaaa", fontsize=10)
        ax.legend(facecolor="#252535", edgecolor="#3a3a4a",
                  labelcolor="#e0e0e0", fontsize=10, loc="upper left")

        self._fig.tight_layout(pad=1.5)
        self._canvas.draw()

    # ── 막대 그래프 (월별 통계) ─────────────────────────────
    def _draw_bar_chart(self, df, year, month):
        self._fig.clear()

        exp_df = df[df["type"] == "지출"].sort_values("total", ascending=False)
        inc_df = df[df["type"] == "수입"].sort_values("total", ascending=False)
        has_e, has_i = not exp_df.empty, not inc_df.empty

        if has_e and has_i:
            # 지출·수입 나란히 (subplot 2개)
            ax1 = self._fig.add_subplot(121, facecolor="#1e1e2e")
            ax2 = self._fig.add_subplot(122, facecolor="#1e1e2e")
            self._single_bar(ax1, exp_df, "지출 분류별", "#f87171")
            self._single_bar(ax2, inc_df, "수입 분류별", "#4ade80")
        elif has_e:
            ax = self._fig.add_subplot(111, facecolor="#1e1e2e")
            self._single_bar(ax, exp_df, f"{year}년 {month}월 지출", "#f87171")
        elif has_i:
            ax = self._fig.add_subplot(111, facecolor="#1e1e2e")
            self._single_bar(ax, inc_df, f"{year}년 {month}월 수입", "#4ade80")
        else:
            self._show_empty_chart(f"{year}년 {month}월 데이터 없음")
            return

        self._fig.suptitle(f"{year}년 {month}월 분류별 내역",
                            color="#e0e0e0", fontsize=12, y=1.01)
        self._fig.tight_layout(pad=1.5)
        self._canvas.draw()

    def _single_bar(self, ax, df, title, color):
        """단일 막대 그래프 헬퍼 – 금액 내림차순 정렬된 df 수신"""
        cats = df["category"].tolist()
        vals = df["total"].tolist()
        bars = ax.bar(range(len(cats)), vals,
                       color=color, alpha=0.82, width=0.6,
                       edgecolor="#1e1e2e", linewidth=0.5)

        # 막대 위에 금액 표시
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    bar.get_height() * 1.01,
                    f"{int(val):,}",
                    ha="center", va="bottom", color="#e0e0e0", fontsize=8)

        ax.set_xticks(range(len(cats)))
        ax.set_xticklabels(cats, rotation=38, ha="right",
                            color="#aaaaaa", fontsize=9)
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
        ax.tick_params(axis="y", colors="#aaaaaa", labelsize=9)
        ax.spines[:].set_color("#3a3a4a")
        ax.grid(axis="y", color="#3a3a4a", linestyle="--", alpha=0.5)
        ax.set_title(title, color="#e0e0e0", fontsize=10, pad=8)

    def _show_empty_chart(self, message):
        """데이터 없을 때 안내 메시지 표시"""
        self._fig.clear()
        ax = self._fig.add_subplot(111, facecolor="#1e1e2e")
        ax.text(0.5, 0.5, message, transform=ax.transAxes,
                ha="center", va="center", color="#666666", fontsize=14)
        ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)
        self._canvas.draw()

    def cleanup(self):
        """앱 종료 시 Figure 메모리 해제"""
        if self._fig:
            import matplotlib.pyplot as plt
            plt.close(self._fig)


# ════════════════════════════════════════════════════════════
# BudgetApp 클래스 – 메인 GUI
# v3.0: 달력 입력 / 수정 기능 / 헤더 정렬 / 글자 크기 / 당월 자동 조회
# ════════════════════════════════════════════════════════════
class BudgetApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.db = Database()

        # ── 상태 변수 ────────────────────────────────────────
        self.selected_id    = None    # 선택된 행의 DB id
        self._edit_mode     = False   # 수정 모드 여부
        self._edit_id       = None    # 수정 중인 거래의 DB id
        self._current_rows  = []      # 현재 화면 데이터 (정렬/수정 참조용)

        # 정렬 상태: True=오름차순 / False=내림차순
        self._sort_asc = {
            "date":     False,   # 기본: 최신 날짜 우선(내림차순)
            "type":     True,
            "category": True,
            "amount":   False,   # 기본: 큰 금액 우선(내림차순)
            "note":     True,
        }
        self._sort_col = "date"   # 마지막으로 정렬한 컬럼

        # 필터: 프로그램 시작 시 이번 달 자동 조회
        today = date.today()
        self._filter_year  = today.year
        self._filter_month = today.month

        self.stats_frame = None   # StatsFrame 참조 (통계 탭)

        # ── 창 설정 ──────────────────────────────────────────
        self.title("💰 심플 가계부")
        self.geometry("1340x840")
        self.minsize(980, 680)

        # ── UI 빌드 ──────────────────────────────────────────
        self._build_layout()
        self._build_left_panel()
        self._build_right_panel()
        self._apply_treeview_style()
        self._build_treeview()

        # 이번 달 데이터 자동 로드
        self.load_data(year=self._filter_year, month=self._filter_month)

        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ════════════════════════════════════════════════════════
    # 레이아웃 뼈대
    # ════════════════════════════════════════════════════════
    def _build_layout(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(self, corner_radius=8, command=self._on_tab_change)
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        # ── 📒 가계부 탭 ─────────────────────────────────────
        gb_tab = self.tabview.add("📒 가계부")
        gb_tab.grid_columnconfigure(0, weight=0)   # 왼쪽 고정
        gb_tab.grid_columnconfigure(1, weight=1)   # 오른쪽 확장
        gb_tab.grid_rowconfigure(0, weight=1)

        self.left_panel = ctk.CTkFrame(gb_tab, width=314, corner_radius=0, fg_color="#1c1c1e")
        self.left_panel.grid(row=0, column=0, sticky="nsew")
        self.left_panel.grid_propagate(False)

        self.right_panel = ctk.CTkFrame(gb_tab, corner_radius=0, fg_color="transparent")
        self.right_panel.grid(row=0, column=1, sticky="nsew", padx=12, pady=12)
        # row 0: 요약 카드  row 1: 필터 바  row 2: 설정 바  row 3: 목록
        self.right_panel.grid_rowconfigure(3, weight=1)
        self.right_panel.grid_columnconfigure(0, weight=1)

        # ── 📊 통계 탭 ───────────────────────────────────────
        stats_tab = self.tabview.add("📊 통계")
        stats_tab.grid_columnconfigure(0, weight=1)
        stats_tab.grid_rowconfigure(0, weight=1)

        if HAS_STATS:
            self.stats_frame = StatsFrame(stats_tab, self.db)
            self.stats_frame.grid(row=0, column=0, sticky="nsew")
        else:
            ctk.CTkLabel(
                stats_tab,
                text="통계 기능을 사용하려면 matplotlib 과 pandas 를 설치해주세요.\n\npip install matplotlib pandas",
                font=ctk.CTkFont(size=14), text_color="#888888",
            ).grid(row=0, column=0)

        self.tabview.set("📒 가계부")

    # ════════════════════════════════════════════════════════
    # 왼쪽 패널 – 입력 폼
    # ════════════════════════════════════════════════════════
    def _build_left_panel(self):
        p = self.left_panel

        ctk.CTkLabel(p, text="💰 심플 가계부",
                     font=ctk.CTkFont(size=21, weight="bold"),
                     text_color="#f0f0f0").pack(pady=(22, 6), padx=20)
        ctk.CTkFrame(p, height=1, fg_color="#3a3a3a").pack(fill="x", padx=18, pady=4)

        form = ctk.CTkScrollableFrame(p, fg_color="transparent",
                                       scrollbar_button_color="#3a3a3a")
        form.pack(fill="both", expand=True, padx=8, pady=6)

        # ─ 날짜 (커스텀 DatePickerButton) ──────────────────
        self._form_label(form, "날짜")
        self.date_entry = DatePickerButton(form)
        self.date_entry.pack(fill="x", padx=10, pady=(0, 10))

        # ─ 구분 ─────────────────────────────────────────────
        self._form_label(form, "구분")
        self.type_var = ctk.StringVar(value="지출")
        self.type_combo = ctk.CTkComboBox(
            form, values=["수입", "저축", "지출"],
            variable=self.type_var,
            command=self._on_type_change,
            height=36, state="readonly",
        )
        self.type_combo.pack(fill="x", padx=10, pady=(0, 10))

        # ─ 분류 ─────────────────────────────────────────────
        self._form_label(form, "분류")
        self.category_var = ctk.StringVar(value="식비")
        self.category_combo = ctk.CTkComboBox(
            form, values=CATEGORIES["지출"],
            variable=self.category_var,
            height=36, state="readonly",
        )
        self.category_combo.pack(fill="x", padx=10, pady=(0, 10))

        # ─ 금액 ─────────────────────────────────────────────
        self._form_label(form, "금액 (원)")
        self.amount_entry = ctk.CTkEntry(form, placeholder_text="숫자만 입력", height=36)
        self.amount_entry.pack(fill="x", padx=10, pady=(0, 10))
        self.amount_entry.bind("<Return>", lambda e: self._on_add_or_update())

        # ─ 비고 ─────────────────────────────────────────────
        self._form_label(form, "비고 (선택)")
        self.note_entry = ctk.CTkEntry(form, placeholder_text="메모를 입력하세요", height=36)
        self.note_entry.pack(fill="x", padx=10, pady=(0, 14))

        # ─ 추가 / 수정 저장 버튼 ────────────────────────────
        # edit mode에 따라 텍스트·색상·동작이 바뀜
        self.add_btn = ctk.CTkButton(
            form, text="＋ 내역 추가",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=44,
            fg_color="#1f6aa5", hover_color="#2980b9",
            command=self._on_add_or_update,
        )
        self.add_btn.pack(fill="x", padx=10, pady=(0, 8))

        # ─ 수정 버튼 + 삭제 버튼 (나란히) ──────────────────
        sub_row = ctk.CTkFrame(form, fg_color="transparent")
        sub_row.pack(fill="x", padx=10, pady=(0, 16))
        sub_row.grid_columnconfigure(0, weight=1)
        sub_row.grid_columnconfigure(1, weight=1)

        # 수정 버튼: edit mode 진입 / edit mode에서는 "취소"로 변경
        self.edit_btn = ctk.CTkButton(
            sub_row, text="✎ 수정",
            height=38,
            fg_color="#3a3a3a", hover_color="#555555",
            command=self._enter_edit_mode,
        )
        self.edit_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        # 삭제 버튼
        self.delete_btn = ctk.CTkButton(
            sub_row, text="✕ 삭제",
            height=38,
            fg_color="#7a1a1a", hover_color="#b03030",
            command=self.delete_transaction,
        )
        self.delete_btn.grid(row=0, column=1, sticky="ew")

        # ── 구분선 ──────────────────────────────────────────
        ctk.CTkFrame(form, height=1, fg_color="#3a3a3a").pack(fill="x", padx=10, pady=4)

        # ─ 전월 이월 금액 ───────────────────────────────────
        self._form_label(form, "전월 이월 금액")
        row_f = ctk.CTkFrame(form, fg_color="transparent")
        row_f.pack(fill="x", padx=10, pady=(0, 6))
        row_f.grid_columnconfigure(0, weight=1)

        self.carryover_entry = ctk.CTkEntry(row_f, placeholder_text="이월 금액 입력", height=36)
        self.carryover_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            row_f, text="저장", width=64, height=36,
            fg_color="#2d6a4f", hover_color="#40916c",
            command=self.save_carryover,
        ).grid(row=0, column=1)

        saved = self.db.get_setting("carryover", "0")
        self.carryover_entry.insert(0, f"{int(saved):,}")

        ctk.CTkLabel(form, text="※ 잔고 = 이월금액 + 수입 − 지출",
                     font=ctk.CTkFont(size=11), text_color="#888888"
                     ).pack(padx=10, pady=(4, 12))

    # ════════════════════════════════════════════════════════
    # 오른쪽 패널 – 요약 카드 + 필터 바 + 설정 바 + 목록
    # ════════════════════════════════════════════════════════
    def _build_right_panel(self):
        rp = self.right_panel

        # ── row 0: 요약 카드 ─────────────────────────────────
        summary = ctk.CTkFrame(rp, fg_color="transparent")
        summary.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        for i in range(4):
            summary.grid_columnconfigure(i, weight=1)

        self.lbl_balance = self._make_card(summary, "현재 잔고",  COLOR_BALANCE, 0)
        self.lbl_income  = self._make_card(summary, "총 수입",    COLOR_INCOME,  1)
        self.lbl_expense = self._make_card(summary, "총 지출",    COLOR_EXPENSE, 2)
        self.lbl_saving  = self._make_card(summary, "총 저축",    COLOR_SAVING,  3)

        # ── row 1: 필터 바 ───────────────────────────────────
        self._build_filter_bar(rp)

        # ── row 2: 설정 바 (글자 크기) ───────────────────────
        self._build_settings_bar(rp)

        # ── row 3: 거래 목록 프레임 ──────────────────────────
        self.list_frame = ctk.CTkFrame(rp, corner_radius=10)
        self.list_frame.grid(row=3, column=0, sticky="nsew")
        self.list_frame.grid_rowconfigure(1, weight=1)
        self.list_frame.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(self.list_frame, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr, text="거래 내역",
                     font=ctk.CTkFont(size=15, weight="bold")).grid(row=0, column=0, sticky="w")

        # 현재 조회 범위 표시 (예: "2024년 4월")
        self.lbl_filter_status = ctk.CTkLabel(
            hdr, text="", font=ctk.CTkFont(size=12), text_color="#888888")
        self.lbl_filter_status.grid(row=0, column=1, sticky="e")

    # ────────────────────────────────────────────────────────
    # 필터 바 – 연도/월 선택 + 조회/전체보기 버튼
    # ────────────────────────────────────────────────────────
    def _build_filter_bar(self, parent):
        bar = ctk.CTkFrame(parent, corner_radius=10, fg_color="#1e1e2e")
        bar.grid(row=1, column=0, sticky="ew", pady=(0, 6))

        ctk.CTkLabel(bar, text="연도", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#aaaaaa").pack(side="left", padx=(14, 4), pady=10)

        year_list = [str(y) for y in self.db.get_distinct_years()]
        self.year_var = ctk.StringVar(value=str(date.today().year))
        self.year_combo = ctk.CTkComboBox(bar, values=year_list, variable=self.year_var,
                                           width=90, height=32, state="readonly")
        self.year_combo.pack(side="left", padx=(0, 12), pady=10)

        ctk.CTkLabel(bar, text="월", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#aaaaaa").pack(side="left", padx=(0, 4), pady=10)

        # 이번 달로 콤보박스 초기화
        self.month_var = ctk.StringVar(value=f"{date.today().month}월")
        self.month_combo = ctk.CTkComboBox(bar, values=MONTHS, variable=self.month_var,
                                            width=80, height=32, state="readonly")
        self.month_combo.pack(side="left", padx=(0, 14), pady=10)

        ctk.CTkButton(bar, text="🔍 조회", width=80, height=32,
                      font=ctk.CTkFont(size=12, weight="bold"),
                      fg_color="#1f538d", hover_color="#2980b9",
                      command=self._on_query).pack(side="left", padx=(0, 6), pady=10)

        ctk.CTkButton(bar, text="전체 보기", width=80, height=32,
                      font=ctk.CTkFont(size=12),
                      fg_color="#3a3a3a", hover_color="#555555",
                      command=self._on_show_all).pack(side="left", pady=10)

        ctk.CTkLabel(bar, text="※ 월 '전체' = 해당 연도 전체",
                     font=ctk.CTkFont(size=11), text_color="#666666"
                     ).pack(side="right", padx=14, pady=10)

    # ────────────────────────────────────────────────────────
    # 설정 바 – 글자 크기 슬라이더
    # ────────────────────────────────────────────────────────
    def _build_settings_bar(self, parent):
        bar = ctk.CTkFrame(parent, corner_radius=10, fg_color="#161622")
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(bar, text="표 글자 크기",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#aaaaaa").pack(side="left", padx=(14, 8), pady=9)

        # 슬라이더: 9pt ~ 18pt, 정수 단계
        self.font_slider = ctk.CTkSlider(
            bar, from_=9, to=18, number_of_steps=9,
            width=160, command=self._on_font_size_change,
        )
        self.font_slider.set(11)   # 기본값 11pt
        self.font_slider.pack(side="left", padx=(0, 6), pady=9)

        # 현재 크기 표시 레이블
        self.lbl_font_size = ctk.CTkLabel(bar, text="11",
                                           width=28,
                                           font=ctk.CTkFont(size=12, weight="bold"),
                                           text_color="#90b8f8")
        self.lbl_font_size.pack(side="left", pady=9)

        ctk.CTkLabel(bar, text="pt",
                     font=ctk.CTkFont(size=11), text_color="#666666"
                     ).pack(side="left", padx=(2, 16), pady=9)

        # 정렬 안내
        ctk.CTkLabel(bar,
                     text="💡 날짜 / 구분 / 분류 / 금액 헤더 클릭 시 정렬  |  행 더블클릭으로 수정",
                     font=ctk.CTkFont(size=11), text_color="#555555"
                     ).pack(side="right", padx=14, pady=9)

    # ════════════════════════════════════════════════════════
    # Treeview 스타일 & 위젯 생성
    # ════════════════════════════════════════════════════════
    def _apply_treeview_style(self, font_size=11):
        """다크 테마 스타일 적용 – font_size 변경 시 재호출 가능"""
        style = ttk.Style()
        style.theme_use("clam")
        row_height = max(24, int(font_size * 2.6))

        style.configure("Treeview",
                         background="#1e1e2e", foreground="#e0e0e0",
                         fieldbackground="#1e1e2e", borderwidth=0,
                         rowheight=row_height, font=("Malgun Gothic", font_size))

        style.configure("Treeview.Heading",
                         background="#12122a", foreground="#90b8f8",
                         font=("Malgun Gothic", 11, "bold"),
                         relief="flat", borderwidth=0)

        style.map("Treeview",
                  background=[("selected", "#1f4e8c")],
                  foreground=[("selected", "#ffffff")])
        style.map("Treeview.Heading",
                  background=[("active", "#1a1a3a")])

        # (DateEntry 제거됨 - DatePickerButton 으로 대체)

    def _build_treeview(self):
        container = tk.Frame(self.list_frame, bg="#1e1e2e")
        container.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        cols = ("no", "date", "type", "category", "amount", "note")
        self.tree = ttk.Treeview(container, columns=cols,
                                  show="headings", selectmode="browse")

        widths  = {"no": 52, "date": 108, "type": 70,
                   "category": 104, "amount": 132, "note": 0}
        anchors = {"no": "center", "date": "center", "type": "center",
                   "category": "center", "amount": "e", "note": "w"}

        for col in cols:
            label = COL_LABELS[col]
            if col == "no":
                # No. 열은 정렬 불필요
                self.tree.heading(col, text=label)
            else:
                # 정렬 가능 컬럼: 헤더 클릭 이벤트 등록
                self.tree.heading(col, text=label,
                                   command=lambda c=col: self._on_sort(c))
            self.tree.column(col, width=widths[col], anchor=anchors[col],
                              stretch=(col == "note"), minwidth=40)

        vsb = ttk.Scrollbar(container, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # 행 색상 태그
        self.tree.tag_configure("income",  foreground="#4ade80")
        self.tree.tag_configure("expense", foreground="#f87171")
        self.tree.tag_configure("saving",  foreground="#60a5fa")
        self.tree.tag_configure("stripe",  background="#252535")
        self.tree.tag_configure("empty",   foreground="#555555")

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-Button-1>",  self._on_row_double_click)   # 더블클릭 → 수정 모드

        # 초기 정렬 화살표 표시 (날짜 내림차순)
        self._update_sort_headers("date")

    # ════════════════════════════════════════════════════════
    # 이벤트 핸들러
    # ════════════════════════════════════════════════════════

    # 구분 변경 → 분류 목록 갱신
    def _on_type_change(self, value):
        cats = CATEGORIES.get(value, [])
        self.category_combo.configure(values=cats)
        if cats:
            self.category_var.set(cats[0])

    # 트리뷰 행 클릭 → DB id 저장
    # iid = str(db_id) 로 저장했으므로 int 변환하면 실제 DB id
    def _on_tree_select(self, _event):
        sel = self.tree.selection()
        if sel:
            try:
                self.selected_id = int(sel[0])
            except ValueError:
                self.selected_id = None   # "데이터 없음" 안내 행 클릭 시 무시

    # 더블클릭 → 수정 모드 진입
    def _on_row_double_click(self, _event):
        if self.selected_id:
            self._enter_edit_mode()

    def _on_closing(self):
        if self.stats_frame:
            self.stats_frame.cleanup()
        self.db.close()
        self.destroy()

    def _on_tab_change(self):
        if self.tabview.get() == "📊 통계" and self.stats_frame:
            self.stats_frame.refresh()

    # 조회 버튼: 연도/월 필터 적용
    def _on_query(self):
        try:
            year = int(self.year_var.get())
        except ValueError:
            messagebox.showwarning("입력 오류", "올바른 연도를 선택해주세요.")
            return
        m_str = self.month_var.get()
        month = None if m_str == "전체" else int(m_str.replace("월", ""))
        self._filter_year  = year
        self._filter_month = month
        self.load_data(year=year, month=month)

    # 전체 보기 버튼: 필터 해제
    def _on_show_all(self):
        self._filter_year  = None
        self._filter_month = None
        self.month_var.set("전체")
        self.load_data()

    # 헤더 클릭 정렬 – 오름차순/내림차순 토글
    def _on_sort(self, col):
        # 같은 컬럼 재클릭 시 방향 반전
        self._sort_asc[col] = not self._sort_asc[col]
        self._sort_col = col
        asc = self._sort_asc[col]
        idx = COL_IDX[col]   # _current_rows 내 해당 컬럼 인덱스

        # 금액은 숫자 비교, 나머지는 문자열 비교
        self._current_rows.sort(key=lambda r: r[idx], reverse=not asc)

        # 헤더 화살표 갱신 후 렌더링
        self._update_sort_headers(col)
        self._render_rows(self._current_rows)

    # 글자 크기 슬라이더 변경
    def _on_font_size_change(self, value):
        size = int(round(value))
        row_height = max(24, int(size * 2.6))

        # 스타일 갱신
        style = ttk.Style()
        style.configure("Treeview", font=("Malgun Gothic", size), rowheight=row_height)
        self.lbl_font_size.configure(text=str(size))

        # ttk.Style 변경은 위젯이 스스로 다시 그리지 않으므로
        # 행 전체를 재삽입하여 강제 리프레시
        self._render_rows(self._current_rows)

    # ════════════════════════════════════════════════════════
    # 비즈니스 로직
    # ════════════════════════════════════════════════════════

    # 추가 vs 수정 분기
    def _on_add_or_update(self):
        if self._edit_mode:
            self._save_edit()
        else:
            self._save_add()

    # ── 거래 추가 ───────────────────────────────────────────
    def _save_add(self):
        date_val     = self.date_entry.get()           # DateEntry.get() → "YYYY-MM-DD"
        type_val     = self.type_var.get()
        category_val = self.category_var.get()
        amount_raw   = self.amount_entry.get().strip().replace(",", "")
        note_val     = self.note_entry.get().strip()

        if not date_val:
            messagebox.showwarning("입력 오류", "날짜를 선택해주세요.")
            return
        if not amount_raw:
            messagebox.showwarning("입력 오류", "금액을 입력해주세요.")
            return
        try:
            amount = int(amount_raw)
            if amount <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("입력 오류", "금액은 양의 정수로 입력해주세요.")
            return

        self.db.add_transaction(date_val, type_val, category_val, amount, note_val)
        self._refresh_year_combo()
        self.amount_entry.delete(0, "end")
        self.note_entry.delete(0, "end")
        self.load_data(year=self._filter_year, month=self._filter_month)
        if self.stats_frame:
            self.stats_frame.refresh_years()

    # ── 수정 저장 (UPDATE) ─────────────────────────────────
    def _save_edit(self):
        if not self._edit_id:
            return

        date_val     = self.date_entry.get()
        type_val     = self.type_var.get()
        category_val = self.category_var.get()
        amount_raw   = self.amount_entry.get().strip().replace(",", "")
        note_val     = self.note_entry.get().strip()

        if not amount_raw:
            messagebox.showwarning("입력 오류", "금액을 입력해주세요.")
            return
        try:
            amount = int(amount_raw)
            if amount <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("입력 오류", "금액은 양의 정수로 입력해주세요.")
            return

        # DB UPDATE (DB PK 기준 처리)
        self.db.update_transaction(self._edit_id, date_val, type_val, category_val, amount, note_val)

        self._exit_edit_mode()         # 수정 모드 종료
        self._refresh_year_combo()
        self.load_data(year=self._filter_year, month=self._filter_month)
        if self.stats_frame:
            self.stats_frame.refresh_years()

    # ── 수정 모드 진입 ─────────────────────────────────────
    # 선택된 행 데이터를 폼에 불러옴
    def _enter_edit_mode(self):
        if not self.selected_id:
            messagebox.showwarning("선택 오류", "수정할 항목을 먼저 선택해주세요.")
            return

        # _current_rows에서 DB id로 원본 데이터 탐색
        row = next((r for r in self._current_rows if r[0] == self.selected_id), None)
        if not row:
            messagebox.showwarning("오류", "해당 항목을 찾을 수 없습니다.")
            return

        db_id, dt, tp, cat, amt, note = row
        self._edit_id   = db_id
        self._edit_mode = True

        # 날짜: DateEntry.set_date()는 datetime.date 객체를 받음
        try:
            self.date_entry.set_date(datetime.strptime(dt, "%Y-%m-%d").date())
        except ValueError:
            pass

        # 구분 → 분류 목록 갱신 → 분류 선택
        self.type_var.set(tp)
        self._on_type_change(tp)
        self.category_var.set(cat)

        # 금액 / 비고
        self.amount_entry.delete(0, "end")
        self.amount_entry.insert(0, str(amt))
        self.note_entry.delete(0, "end")
        self.note_entry.insert(0, note or "")

        # 버튼 상태 변경 (수정 모드 표시)
        self.add_btn.configure(text="✓ 수정 저장", fg_color="#2d6a4f", hover_color="#40916c")
        self.edit_btn.configure(text="✕ 수정 취소", fg_color="#555555", hover_color="#777777",
                                 command=self._exit_edit_mode)
        self.delete_btn.configure(state="disabled", fg_color="#2a1a1a")   # 수정 중 삭제 방지

    # ── 수정 모드 종료 → 폼/버튼 초기화 ────────────────────
    def _exit_edit_mode(self):
        self._edit_mode = False
        self._edit_id   = None

        self.date_entry.set_date(date.today())
        self.type_var.set("지출")
        self._on_type_change("지출")
        self.amount_entry.delete(0, "end")
        self.note_entry.delete(0, "end")

        self.add_btn.configure(text="＋ 내역 추가", fg_color="#1f6aa5", hover_color="#2980b9")
        self.edit_btn.configure(text="✎ 수정", fg_color="#3a3a3a", hover_color="#555555",
                                 command=self._enter_edit_mode)
        self.delete_btn.configure(state="normal", fg_color="#7a1a1a")

    # ── 삭제 ───────────────────────────────────────────────
    def delete_transaction(self):
        if not self.selected_id:
            messagebox.showwarning("선택 오류", "삭제할 항목을 먼저 선택해주세요.")
            return
        if messagebox.askyesno("삭제 확인", "선택한 항목을 삭제하시겠습니까?"):
            self.db.delete_transaction(self.selected_id)
            self.selected_id = None
            self._refresh_year_combo()
            self.load_data(year=self._filter_year, month=self._filter_month)
            if self.stats_frame:
                self.stats_frame.refresh_years()

    # ── 이월금액 저장 ───────────────────────────────────────
    def save_carryover(self):
        raw = self.carryover_entry.get().strip().replace(",", "")
        try:
            amount = int(raw) if raw else 0
            if amount < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("입력 오류", "이월 금액은 0 이상의 정수로 입력해주세요.")
            return
        self.db.set_setting("carryover", str(amount))
        self.carryover_entry.delete(0, "end")
        self.carryover_entry.insert(0, f"{amount:,}")
        self.update_summary(year=self._filter_year, month=self._filter_month)
        messagebox.showinfo("저장 완료", f"이월 금액 {amount:,} 원이 저장되었습니다.")

    # ════════════════════════════════════════════════════════
    # 데이터 로드 & 렌더링
    # ════════════════════════════════════════════════════════

    def load_data(self, year=None, month=None):
        """DB 조회 → _current_rows 저장 → 화면 렌더링"""
        rows = self.db.get_all_transactions(year=year, month=month)
        self._current_rows = list(rows)        # 정렬/수정 참조용 원본 보관
        self._render_rows(self._current_rows)
        self._update_filter_status(year, month)
        self.update_summary(year=year, month=month)

    def _render_rows(self, rows):
        """트리뷰 전체 갱신 + No.를 1부터 순차 재할당 (DB PK와 독립적)"""
        # 기존 행 전체 삭제
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not rows:
            period = self._format_period(self._filter_year, self._filter_month)
            self.tree.insert("", "end",
                             values=("", "", "", f"─── {period} 내역이 없습니다 ───", "", ""),
                             tags=("empty",))
            return

        for seq, (row_id, dt, tp, cat, amt, note) in enumerate(rows, start=1):
            # seq: 화면 표시용 순번 (항상 1부터 연속)
            # row_id: DB PK → iid로 저장하여 선택 시 복원
            color_tag = {"수입": "income", "지출": "expense", "저축": "saving"}.get(tp, "")
            tags      = (color_tag, "stripe") if seq % 2 == 0 else (color_tag,)

            self.tree.insert("", "end",
                             iid=str(row_id),          # iid = DB PK (문자열)
                             values=(seq, dt, tp, cat, f"{amt:,} 원", note or ""),
                             tags=tags)

    def update_summary(self, year=None, month=None):
        income, expense, saving = self.db.get_summary(year=year, month=month)

        if year and month:
            # 월별 조회: 해당 월 이전 누적 잔고를 이월금액으로 자동 계산
            carryover = self.db.get_balance_before(year, month)
        else:
            # 전체/연도 조회: 저장된 이월금액 사용
            carryover = int(self.db.get_setting("carryover", "0"))

        balance = carryover + income - expense
        self.lbl_balance.configure(text=f"{balance:,} 원")
        self.lbl_income.configure(text=f"{income:,} 원")
        self.lbl_expense.configure(text=f"{expense:,} 원")
        self.lbl_saving.configure(text=f"{saving:,} 원")

    # ════════════════════════════════════════════════════════
    # UI 헬퍼
    # ════════════════════════════════════════════════════════

    def _form_label(self, parent, text):
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#aaaaaa").pack(anchor="w", padx=10, pady=(8, 2))

    def _make_card(self, parent, title, bg_color, col):
        card = ctk.CTkFrame(parent, fg_color=bg_color, corner_radius=12)
        card.grid(row=0, column=col, padx=5, pady=4, sticky="ew")
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=12),
                     text_color="#aaaaaa").pack(pady=(14, 2))
        lbl = ctk.CTkLabel(card, text="0 원",
                            font=ctk.CTkFont(size=22 if title == "현재 잔고" else 18, weight="bold"),
                            text_color="#ffffff")
        lbl.pack(pady=(0, 14))
        return lbl

    def _refresh_year_combo(self):
        """거래 추가/삭제 후 연도 콤보박스 목록 갱신"""
        year_list = [str(y) for y in self.db.get_distinct_years()]
        current   = self.year_var.get()
        self.year_combo.configure(values=year_list)
        if current not in year_list and year_list:
            self.year_var.set(year_list[0])

    def _update_filter_status(self, year, month):
        self.lbl_filter_status.configure(text=self._format_period(year, month))

    def _format_period(self, year, month):
        if year is None:  return "전체 내역"
        if month is None: return f"{year}년 전체"
        return f"{year}년 {month}월"

    def _update_sort_headers(self, sorted_col):
        """정렬 중인 컬럼 헤더에 화살표 표시, 나머지는 원래 이름으로 복원"""
        for col in COL_IDX:
            label = COL_LABELS[col]
            if col == sorted_col:
                self.tree.heading(col, text=label + ARROW[self._sort_asc[col]])
            else:
                self.tree.heading(col, text=label)


# ════════════════════════════════════════════════════════════
# 진입점
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = BudgetApp()
    app.mainloop()

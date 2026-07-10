import json
import base64
import ssl
import urllib.request
import urllib.parse
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import datetime
import tempfile
import platform
import subprocess
import traceback
from src.api.auth import get_token
from src.api.http_client import build_opener
from src.api.rating import call_rating, summarize_rates
from src.config import (
    UPS_CLIENT_ID,
    UPS_CLIENT_SECRET,
    UPS_SHIPPER_NUMBER,
)

SERVICE_CODE_MAP = {
    "01": "UPS Next Day Air",
    "02": "UPS 2nd Day Air",
    "03": "UPS Ground",
    "07": "UPS Worldwide Express",
    "08": "UPS Worldwide Expedited",
    "11": "UPS Standard",
    "12": "UPS 3 Day Select",
    "13": "UPS Next Day Air Saver",
    "14": "UPS Next Day Air Early",
    "54": "UPS Worldwide Express Plus",
    "59": "UPS 2nd Day Air A.M.",
    "65": "UPS Worldwide Saver",
    "70": "UPS Access Point Economy",
    "71": "UPS Worldwide Express Freight Midday",
    "72": "UPS Worldwide Express Freight",
    "74": "UPS Express 12:00",
    "82": "UPS Today Standard",
    "83": "UPS Today Dedicated Courier",
    "84": "UPS Today Intercity",
    "85": "UPS Today Express",
    "86": "UPS Today Express Saver",
    "96": "UPS Worldwide Express Freight (Pallet)"
}

PACKAGING_TYPES = {
    "01": "UPS Letter (서류)",
    "02": "일반 상자 (Customer Supplied Package)",
    "30": "Pallet (팔레트)"
}


# ---------------- GUI ----------------
root = tk.Tk()
root.title("UPS 수출/수입 물류비 실시간 예상운임 조회 시스템")
root.geometry("1200x950")

default_font = ("맑은 고딕", 11)
root.option_add("*Font", default_font)
style = ttk.Style()
style.configure("Treeview", rowheight=28, font=("맑은 고딕", 11))
style.configure("Treeview.Heading", font=("맑은 고딕", 12, "bold"))
style.configure("GetQuote.TButton", font=("맑은 고딕", 22, "bold"), padding=(30, 20))

main = ttk.Frame(root, padding=12)
main.pack(fill="both", expand=True)

# 💡 [UI 추가] 수출 / 수입 업무 모드 선택기
mode_frame = ttk.LabelFrame(main, text="물류 프로세스 선택")
mode_frame.pack(fill="x", pady=(0, 8))

trade_mode_var = tk.StringVar(value="EXPORT") # EXPORT 또는 IMPORT
ttk.Radiobutton(mode_frame, text="국내 ➔ 해외 배송 (수출 - Export)", variable=trade_mode_var, value="EXPORT").grid(row=0, column=0, padx=20, pady=8)
ttk.Radiobutton(mode_frame, text="해외 ➔ 국내 수입 (수입 착불 - Import Collect)", variable=trade_mode_var, value="IMPORT").grid(row=0, column=1, padx=20, pady=8)

# 해외 파트너 정보 (수출 시 목적지 / 수입 시 발송지)
dest = ttk.LabelFrame(main, text="해외 파트너 주소 정보")
dest.pack(fill="x", pady=(0, 8))

ttk.Label(dest, text="국가코드*(예:US)").grid(row=0, column=0, sticky="w", padx=5, pady=5)
to_country_var = tk.StringVar(value="US")
ttk.Entry(dest, textvariable=to_country_var, width=8).grid(row=0, column=1, padx=(6, 12))

ttk.Label(dest, text="ZIP/우편번호*").grid(row=0, column=2, sticky="w", padx=5, pady=5)
to_zip_var = tk.StringVar(value="78852")
zip_entry = ttk.Entry(dest, textvariable=to_zip_var, width=12)
zip_entry.grid(row=0, column=3, padx=(6, 12))

ttk.Label(dest, text="주(STATE, 선택)").grid(row=0, column=4, sticky="w", padx=5, pady=5)
to_state_var = tk.StringVar(value="TX")
ttk.Entry(dest, textvariable=to_state_var, width=8).grid(row=0, column=5, padx=(6, 12))

ttk.Label(dest, text="도시(CITY, 선택)").grid(row=0, column=6, sticky="w", padx=5, pady=5)
to_city_var = tk.StringVar(value="Eagle Pass")
ttk.Entry(dest, textvariable=to_city_var, width=18).grid(row=0, column=7, padx=(6, 12))

def resolve_zip_city_state():
    try:
        cc = to_country_var.get().strip().upper()
        z = to_zip_var.get().strip()
        if cc != "US" or not z or len(z) < 5: return
        opener = build_opener()
        with opener.open(f"https://api.zippopotam.us/us/{z}", timeout=8) as resp:
            if resp.getcode() != 200: return
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        places = data.get("places") or []
        if not places: return
        st = places[0].get("state abbreviation") or ""
        city = places[0].get("place name") or ""
        if st: to_state_var.set(st)
        if city: to_city_var.set(city)
    except Exception: pass

zip_entry.bind("<FocusOut>", lambda e: resolve_zip_city_state())
zip_entry.bind("<Return>", lambda e: resolve_zip_city_state())

# 환경/자격
cred = ttk.LabelFrame(main, text="UPS 한국 정산 계정 정보")
cred.pack(fill="x", pady=(0, 8))

env_var = tk.StringVar(value="PROD")
ttk.Label(cred, text="환경").grid(row=0, column=0, sticky="w", padx=5, pady=5)
ttk.Radiobutton(cred, text="Production (운영)", variable=env_var, value="PROD").grid(row=0, column=1, padx=6)
ttk.Radiobutton(cred, text="Test (CIE 환경)", variable=env_var, value="TEST").grid(row=0, column=2, padx=6)

ttk.Label(cred, text="청구 계정번호").grid(row=1, column=0, sticky="w", padx=5, pady=5)
shipper_var = tk.StringVar(value=UPS_SHIPPER_NUMBER)
ttk.Entry(cred, textvariable=shipper_var, width=20, state="readonly").grid(row=1, column=1, sticky="w", padx=(6,12))

ttk.Label(cred, text="회사명").grid(row=1, column=2, sticky="w", padx=5, pady=5)
shipper_name_var = tk.StringVar(value="ECO CAB")
ttk.Entry(cred, textvariable=shipper_name_var, width=30, state="readonly").grid(row=1, column=3, sticky="w", padx=(6,12))

# 패키지 추가
pkg_frame = ttk.LabelFrame(main, text="패키지 명세 입력 (최대 50개)")
pkg_frame.pack(fill="x", pady=(0, 8))

ttk.Label(pkg_frame, text="포장형태").grid(row=0, column=0, sticky="w")
pkg_type_var = tk.StringVar()
pkg_type_cb = ttk.Combobox(pkg_frame, textvariable=pkg_type_var, width=34, state="readonly",
                           values=[f"{k} {v}" for k, v in PACKAGING_TYPES.items()])
pkg_type_cb.grid(row=0, column=1, padx=(6, 12))
pkg_type_cb.set("02 " + PACKAGING_TYPES.get("02"))

ttk.Label(pkg_frame, text="무게(KG)*").grid(row=0, column=2, sticky="w")
pkg_weight_var = tk.StringVar(value="2.0")
ttk.Entry(pkg_frame, textvariable=pkg_weight_var, width=10).grid(row=0, column=3, padx=(6, 12))

ttk.Label(pkg_frame, text="가로 x 세로 x 높이 (CM, 선택)").grid(row=0, column=4, sticky="w")
pkg_len_var = tk.StringVar(value="30")
pkg_wid_var = tk.StringVar(value="20")
pkg_hei_var = tk.StringVar(value="10")
ttk.Entry(pkg_frame, textvariable=pkg_len_var, width=6).grid(row=0, column=5, padx=(6, 6))
ttk.Entry(pkg_frame, textvariable=pkg_wid_var, width=6).grid(row=0, column=6, padx=(0, 6))
ttk.Entry(pkg_frame, textvariable=pkg_hei_var, width=6).grid(row=0, column=7, padx=(0, 6))

add_btn = ttk.Button(pkg_frame, text="추가")
add_btn.grid(row=0, column=8, padx=(8, 0))
del_btn = ttk.Button(pkg_frame, text="선택 삭제")
del_btn.grid(row=0, column=9, padx=(8, 0))
clear_btn = ttk.Button(pkg_frame, text="전체 삭제")
clear_btn.grid(row=0, column=10, padx=(8, 0))

# 빠른 입력
quick_frame = ttk.LabelFrame(main, text="빠른 대량 입력 (총량 분할 방식)")
quick_frame.pack(fill="x", pady=(0, 8))

ttk.Label(quick_frame, text="총 무게(KG)").grid(row=0, column=0, sticky="w")
total_weight_var = tk.StringVar(value="")
ttk.Entry(quick_frame, textvariable=total_weight_var, width=12).grid(row=0, column=1, padx=(6, 12))

ttk.Label(quick_frame, text="박스 개수").grid(row=0, column=2, sticky="w")
box_count_var = tk.StringVar(value="")
ttk.Entry(quick_frame, textvariable=box_count_var, width=8).grid(row=0, column=3, padx=(6, 12))

# 패키지 목록
pkg_list_frame = ttk.LabelFrame(main, text="입력된 화물 패키지 리스트")
pkg_list_frame.pack(fill="both", expand=True, pady=(0, 8))

pkg_tree = ttk.Treeview(pkg_list_frame, columns=("idx", "type", "w", "l", "wi", "h"), show="headings", height=3)
for col, txt, w in [
    ("idx", "#", 40), ("type", "포장코드", 80), ("w", "무게(KG)", 80),
    ("l", "가로(CM)", 60), ("wi", "세로(CM)", 60), ("h", "높이(CM)", 60),
]:
    pkg_tree.heading(col, text=txt)
    pkg_tree.column(col, width=w, anchor="center")

scrollbar = ttk.Scrollbar(pkg_list_frame, orient="vertical", command=pkg_tree.yview)
pkg_tree.configure(yscroll=scrollbar.set)
pkg_tree.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

def _reindex_pkg_tree():
    for i, item in enumerate(pkg_tree.get_children(), start=1):
        vals = list(pkg_tree.item(item, "values"))
        vals[0] = i
        pkg_tree.item(item, values=vals)

def quick_fill_tree():
    if pkg_tree.get_children():
        messagebox.showwarning("안내", "이미 리스트에 화물이 존재합니다. 비우고 사용해 주세요.")
        return
    tw_raw = (total_weight_var.get() or "").strip()
    bc_raw = (box_count_var.get() or "").strip()
    if not tw_raw or not bc_raw: return
    try:
        total_w = float(tw_raw)
        box_cnt = int(bc_raw)
        if total_w <= 0 or box_cnt <= 0: raise ValueError
    except Exception: return

    if box_cnt > 50: box_cnt = 50
    base = round(total_w / box_cnt, 3)
    acc = 0.0
    for i in range(1, box_cnt + 1):
        if i < box_cnt: w = base; acc += w
        else:
            w = round(total_w - acc, 3)
            if w <= 0: w = base
        idx = len(pkg_tree.get_children()) + 1
        pkg_tree.insert("", "end", values=(idx, "02", f"{w}", "", "", ""))
    if len(pkg_tree.get_children()) >= 50: add_btn["state"] = "disabled"

ttk.Button(quick_frame, text="패키지 일괄 생성", command=quick_fill_tree).grid(row=0, column=4, padx=(6, 0))

# 요금 결과
rate_frame = ttk.LabelFrame(main, text="UPS 실시간 예상 운임 결과 (할인요금 최저가 정렬)")
rate_frame.pack(fill="both", expand=True, pady=(0, 8))

rate_tree = ttk.Treeview(rate_frame, columns=("code", "desc", "bill_wt", "list", "neg", "ccy"), show="headings", height=4)
for col, txt, w in [
    ("code", "코드", 80), ("desc", "UPS 서비스명", 280), ("bill_wt", "청구 무게(KG)", 140),
    ("list", "Published(정가)", 140), ("neg", "Negotiated(계약할인가)", 140), ("ccy", "통화", 70),
]:
    rate_tree.heading(col, text=txt)
    rate_tree.column(col, width=w, anchor="center")
rate_tree.pack(fill="both", expand=True)

# 하단 제어부
controls = ttk.Frame(main)
controls.pack(fill="x", pady=(6, 0))
status = tk.StringVar(value="시스템 준비 완료.")
ttk.Label(controls, textvariable=status, font=("맑은 고딕", 11, "bold")).pack(side="left")

actions = ttk.Frame(main)
actions.pack(fill="x", pady=(4, 8))
auto_log_var = tk.BooleanVar(value=True)
ttk.Checkbutton(actions, text="자동 쿼리 로그 저장", variable=auto_log_var).pack(side="left")
ttk.Button(actions, text="결과 CSV 저장", command=lambda: save_results_as_csv()).pack(side="left", padx=(12,0))
ttk.Button(actions, text="로그 폴더 열기", command=lambda: _open_folder(_get_log_base_dir())).pack(side="left", padx=(8,0))

def _get_log_base_dir():
    env_dir = os.environ.get("UPS_RATE_LOG_DIR")
    if env_dir:
        try: os.makedirs(env_dir, exist_ok=True); return env_dir
        except Exception: pass
    try:
        docs = os.path.join(os.path.expanduser("~"), "Documents", "UPS_Rate_Logs")
        os.makedirs(docs, exist_ok=True)
        return docs
    except Exception: pass
    tmp = os.path.join(tempfile.gettempdir(), "UPS_Rate_Logs")
    os.makedirs(tmp, exist_ok=True)
    return tmp

def _mask_sensitive(obj):
    try:
        data = json.loads(json.dumps(obj))

        charge = (
            data.get("RateRequest", {})
            .get("Shipment", {})
            .get("PaymentDetails", {})
            .get("ShipmentCharge", [{}])[0]
        )

        for billing_key in (
            "BillShipper",
            "BillReceiver",
            "BillThirdParty",
        ):
            billing = charge.get(billing_key)

            if not isinstance(billing, dict):
                continue

            account = str(billing.get("AccountNumber", ""))

            if account:
                if len(account) >= 3:
                    masked = (
                        account[:2]
                        + "*" * max(len(account) - 3, 1)
                        + account[-1:]
                    )
                else:
                    masked = "***"

                billing["AccountNumber"] = masked

        return data

    except Exception:
        return obj

def save_results_as_csv(default_path=None):
    try:
        rows = []
        for iid in rate_tree.get_children(): rows.append(rate_tree.item(iid, "values"))
        if not rows: return
        cols = ["service_code", "service_desc", "billing_weight", "list_total", "negotiated_total", "currency"]
        if default_path is None:
            fp = filedialog.asksaveasfilename(
                title="결과 저장 (CSV)", defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")],
                initialfile=f"ups_rates_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )
            if not fp: return
        else: fp = default_path
        import csv
        with open(fp, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(cols)
            for r in rows: writer.writerow(r)
    except Exception as e: pass

def add_package():
    if len(pkg_tree.get_children()) >= 50: return
    w_raw = pkg_weight_var.get().strip()
    if not w_raw: return
    try:
        w = float(w_raw)
        if w <= 0: raise ValueError
    except Exception: return

    l_raw, wi_raw, h_raw = pkg_len_var.get().strip(), pkg_wid_var.get().strip(), pkg_hei_var.get().strip()
    l = wi = h = ""
    if l_raw or wi_raw or h_raw:
        try:
            if not (l_raw and wi_raw and h_raw): raise ValueError
            if float(l_raw) <= 0 or float(wi_raw) <= 0 or float(h_raw) <= 0: raise ValueError
            l, wi, h = str(float(l_raw)), str(float(wi_raw)), str(float(h_raw))
        except Exception: return

    pcode = pkg_type_var.get().split()[0]
    idx = len(pkg_tree.get_children()) + 1
    pkg_tree.insert("", "end", values=(idx, pcode, f"{w}", l, wi, h))
    if len(pkg_tree.get_children()) >= 50: add_btn["state"] = "disabled"

def remove_selected_package():
    for iid in pkg_tree.selection(): pkg_tree.delete(iid)
    _reindex_pkg_tree()
    if len(pkg_tree.get_children()) < 50: add_btn["state"] = "normal"

def clear_all_packages():
    pkg_tree.delete(*pkg_tree.get_children())
    add_btn["state"] = "normal"

def build_packages_array():
    items = []
    for item in pkg_tree.get_children():
        idx, pcode, w, l, wi, h = pkg_tree.item(item, "values")
        pkg = {
            "PackagingType": {"Code": str(pcode)},
            "PackageWeight": {"UnitOfMeasurement": {"Code": "KGS"}, "Weight": str(w)},
        }
        if str(l).strip() and str(wi).strip() and str(h).strip():
            pkg["Dimensions"] = {
                "UnitOfMeasurement": {"Code": "CM"},
                "Length": str(l).strip(), "Width": str(wi).strip(), "Height": str(h).strip(),
            }
        items.append(pkg)
    return items

# 💡 [핵심 엔진 수정] 수출 / 수입 분기 동적 페이로드 제어기
def on_get_rates():
    try:
        mode = trade_mode_var.get() # EXPORT 또는 IMPORT
        partner_country = to_country_var.get().strip().upper()
        partner_zip = to_zip_var.get().strip()
        partner_city = to_city_var.get().strip()
        partner_state = to_state_var.get().strip()

        if not partner_country or not partner_zip:
            messagebox.showerror("오류", "해외 파트너의 국가코드와 우편번호는 필수입니다.")
            return

        packages = build_packages_array()
        if not packages:
            quick_fill_tree()
            packages = build_packages_array()

        if not packages:
            messagebox.showwarning("패키지 없음", "화물 명세를 구성해 주세요.")
            return

        # 1. 공통 한국 주소 객체 선언
        kr_address = {
            "AddressLine": ["94-3 Mullae-ro"],
            "City": "Seoul",
            "CountryCode": "KR",
            "PostalCode": "07295"
        }

        # 2. 공통 해외 주소 객체 선언
        partner_address = {
            "CountryCode": partner_country,
            "PostalCode": partner_zip,
            "City": partner_city or "CityName",
            "StateProvinceCode": partner_state or None
        }
        if partner_address["StateProvinceCode"] is None:
            del partner_address["StateProvinceCode"]

        # 💡 모드에 따른 동적 Shipment 트리 구성
        if mode == "EXPORT":
            # 한국에서 발송하여 해외로 수출하는 구조
            shipment = {
                "Shipper": {
                    "Name": "ECO CAB",
                    "ShipperNumber": UPS_SHIPPER_NUMBER,
                    "Address": kr_address
                },
                "ShipFrom": {
                    "Name": "ECO CAB Factory",
                    "Address": kr_address
                },
                "ShipTo": {
                    "Name": "Global Partner",
                    "Address": partner_address
                },
                "PaymentDetails": {
                    "ShipmentCharge": [
                        {
                            "Type": "01",
                            "BillShipper": {"AccountNumber": UPS_SHIPPER_NUMBER}
                        }
                    ]
                }
            }
        else:
            # 💡 [수입 Collect 핵심] 해외에서 발송하여 한국으로 가져오는 구조 (111595 에러 원천 차단)
            shipment = {
                "Shipper": {
                    "Name": "Foreign Supplier",
                    # 수입 시 여기 ShipperNumber를 넣으면 계정 인증 에러가 발생하므로 제거
                    "Address": partner_address
                },
                "ShipFrom": {
                    "Name": "Foreign Factory",
                    "Address": partner_address
                },
                "ShipTo": {
                    "Name": "ECO CAB",
                    "Address": kr_address
                },
                "PaymentDetails": {
                    "ShipmentCharge": [
                        {
                            "Type": "01", 
                            "BillReceiver": { # 💡 제3자 정산이 아닌 수화인(한국 수입자) 직권 청구 맵핑
                                "AccountNumber": UPS_SHIPPER_NUMBER,
                                "Address": {
                                    "CountryCode": "KR",
                                    "PostalCode": "44936"
                                }
                            }
                        }
                    ]
                }
            }

        # 패키지 및 계약요금 활성화 인디케이터 바인딩
        shipment["Package"] = packages
        shipment["ShipmentRatingOptions"] = {
            "NegotiatedRatesIndicator": "Y",
            "UserLevelDiscountIndicator": "Y"
        }

        selected_code = pkg_type_var.get().split()[0]
        if selected_code == "30":
            shipment["NumOfPieces"] = str(len(packages))
            allowed = {"71", "72", "96"}
        else:
            allowed = {"07", "08", "65"}

        base_url = "https://onlinetools.ups.com" if env_var.get() == "PROD" else "https://wwwcie.ups.com"

        btn["state"] = "disabled"
        status.set(f"[{mode}] 토큰 갱신 중...")
        root.update_idletasks()

        token = get_token(base_url)

        status.set(f"[{mode}] UPS 실시간 요금 조회 중...")
        root.update_idletasks()
        
        raw = call_rating(base_url, token, shipment)

        # 로그 저장 프로세스
        if auto_log_var.get():
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            log_dir = os.path.join(_get_log_base_dir(), ts)
            os.makedirs(log_dir, exist_ok=True)
            payload = {"RateRequest": {"Request": {"TransactionReference":{"CustomerContext":"tk-rate"},"RequestOption":"Shop"}, "Shipment": shipment}}
            _write_json(os.path.join(log_dir, "request.json"), _mask_sensitive(payload))
            _write_json(os.path.join(log_dir, "response.json"), raw)
            csv_path = os.path.join(log_dir, f"rates_{ts}.csv")
            save_results_as_csv(default_path=csv_path)

        rows = summarize_rates(raw,service_code_map=SERVICE_CODE_MAP,)
        rows = [r for r in rows if r.get("service_code") in allowed]

        for i in rate_tree.get_children(): rate_tree.delete(i)
        for r in rows:
            rate_tree.insert(
                "", "end",
                values=(
                    r.get("service_code", ""),
                    SERVICE_CODE_MAP.get(r.get("service_code", ""), r.get("service_desc", "")),
                    r.get("billing_weight", ""),
                    f"{r.get('list_total', 0):,.2f}" if r.get('list_total') is not None else "",
                    f"{r.get('negotiated_total', 0):,.2f}" if r.get('negotiated_total') is not None else "",
                    r.get("currency", ""),
                ),
            )

        status.set(f"[{mode}] 조회 성공. {len(rows)}개 운임 필터링 완료.")
    except Exception as e:
        traceback.print_exc()
        messagebox.showerror("조회 실패", str(e))
        status.set("오류 발생으로 조회가 중단되었습니다.")
    finally:
        btn["state"] = "normal"

def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

add_btn.configure(command=add_package)
del_btn.configure(command=remove_selected_package)
clear_btn.configure(command=clear_all_packages)

btn = ttk.Button(root, text="실시간 예상 운임 조회 (Get Quote)", command=on_get_rates, style="GetQuote.TButton")
btn.pack(pady=15, padx=12, fill="x")

root.mainloop()
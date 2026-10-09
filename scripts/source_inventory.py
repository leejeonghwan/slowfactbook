#!/usr/bin/env python3
"""Build a read-only source audit. Does not fetch, refresh, assign IDs or publish.

python3 scripts/source_inventory.py
Review decisions live in reports/source_reviews.json, keyed by audit_key.
The report never treats inferred frequency as a confirmed release schedule.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read_json(path, errors):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        errors.append({"file": path.name, "error": str(exc)})
        return {}


def time_axis(labels, frequency):
    labs = [str(x).strip() for x in labels]
    nonempty = [x for x in labs if x]
    freq = {"Y": "연", "A": "연", "Q": "분기", "M": "월", "W": "주", "D": "일"}.get(frequency)
    if not nonempty:
        return freq or "미확인", "빈 시점", "연결 설정" if freq else "판정 불가"
    years = [x for x in nonempty if re.fullmatch(r"(?:19|20)\d{2}년?", x)]
    if years and (len(set(years)) < len(years) or len(labs) > len(nonempty)):
        return freq or "미확인", "연도 축약·빈칸: 원시점 대조 필요", "연결 설정" if freq else "반복 연도로 주기 확정 불가"
    patterns = [("일·주", r"(?:19|20)\d{2}[-./]\d{1,2}[-./]\d{1,2}"),
                ("월", r"(?:19|20)\d{2}[-./](?:0?[1-9]|1[0-2])"),
                ("분기", r"(?:19|20)\d{2}\s*[-.]?\s*(?:[1-4]\s*[Qq분기]+|[Qq][1-4])")]
    for guessed, pattern in patterns:
        if all(re.fullmatch(pattern, x) for x in nonempty):
            return freq or guessed, "형식 확인·원자료 대조 전", "연결 설정" if freq else "라벨 추정"
    if len(years) == len(nonempty):
        issue = "연도만 있음: 원시점 대조 필요" if freq in {"월", "분기", "일", "주"} else "연도 표기·원자료 대조 전"
        return freq or "연", issue, "연결 설정" if freq else "라벨 추정"
    return freq or "미확인", "축 의미·시점 확인 필요", "연결 설정" if freq else "비시계열 또는 축약 시점"


def build(data_dir, reviews):
    errors, rows, seen = [], [], set()
    ids = read_json(data_dir / "ids.json", errors)
    overrides = read_json(data_dir / "overrides.json", errors)
    mappings = {**read_json(data_dir / "api_map.json", errors),
                **read_json(data_dir / "api_map_auto.json", errors)}
    api = read_json(data_dir / "api_charts.json", errors)
    kb = read_json(data_dir / "kb_charts.json", errors)
    occurrences = Counter()
    for path in sorted(data_dir.glob("*.json")):
        # Only chart containers; other files include reviews and source metadata.
        if path.name.startswith("_"):
            continue
        doc = read_json(path, errors)
        if not isinstance(doc, dict) or not isinstance(doc.get("items"), list):
            continue
        for index, original in enumerate(doc["items"]):
            if not original.get("vizType"):
                continue
            slide = str(original.get("slide", ""))
            title = str(original.get("title", "")).strip().rstrip(".")
            base = "\x1f".join(["S", slide, title])
            occurrences[base] += 1
            idkey = base if occurrences[base] == 1 else base + "\x1f" + str(occurrences[base])
            cid = original.get("id") or ids.get(idkey, "")
            item = {**original, **(overrides.get(cid) or overrides.get(slide) or {})}
            fingerprint = json.dumps([item.get(k) for k in ("title", "vizType", "labels", "series", "source", "sourceUrl")], ensure_ascii=False, sort_keys=True)
            digest = hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
            if digest in seen:
                continue
            seen.add(digest)
            # Location key avoids conflating multiple charts with identical titles/IDs.
            audit_key = f"{path.name}:{slide}:{index}"
            spec = mappings.get(cid) or mappings.get(slide) or api.get(slide) or {}
            track = "API 설정" if spec else "미등록"
            if cid in kb:
                spec, track = kb[cid], "엑셀 입력"
            elif slide in {"slide-570", "slide-571"}:
                track = "PDF 수집 설정"
                spec = {"provider": "realmeter", "sourceUrl": "http://www.realmeter.net/category/pdf/", "prdSe": "W"}
            source = str(item.get("source") or spec.get("source") or "").strip()
            url = str(spec.get("sourceUrl") or item.get("sourceUrl") or "").strip()
            status = "연결 설정 있음" if spec else "링크 있음·미검증" if url else "출처명만 있음" if source else "출처 미기재"
            freq, axis_issue, basis = time_axis(item.get("labels") or [], spec.get("prdSe") or spec.get("cycle"))
            names = item.get("seriesNames") or []
            nseries = len(item.get("series") or [])
            legend_issue = len(names) != nseries or any(not str(x or "").strip() or re.fullmatch(r"(?:계열|Series)\s*\d+", str(x), re.I) for x in names)
            if names and len(set(str(x) for x in names)) != len(names):
                legend_issue = True
            source_identity = {k: spec[k] for k in ("provider", "orgId", "tblId", "sheet") if k in spec}
            if not source_identity and url:
                source_identity = {"url": url}
            source_id = "src-" + hashlib.sha256(json.dumps(source_identity, sort_keys=True).encode()).hexdigest()[:12] if source_identity else ""
            labels = item.get("labels") or []
            row = {
                "audit_key": audit_key, "chart_id": cid, "slide": slide,
                "title": item.get("title") or "(제목 없음)", "category": item.get("category") or doc.get("category") or "",
                "source_status": status, "source_id": source_id, "source_text": source, "source_url": url,
                "official_table_name": spec.get("_tblNm") or spec.get("table") or spec.get("sheet") or "",
                "connection": track, "source_definition": source_identity,
                "series_selector": {k: spec[k] for k in ("itmId", "objL1", "objL2", "objL3", "objL4", "series", "scale", "unit") if k in spec},
                "data_frequency": freq, "frequency_basis": basis,
                "release_frequency": "미확인", "release_evidence_url": "",
                "proposed_check_frequency": {"연": "연 1회", "분기": "분기", "월": "월간", "주": "주간", "일": "주간", "일·주": "주간"}.get(freq, "출처 확인 후 결정"),
                "confirmed_check_frequency": "미확정", "update_mode": "자동 갱신 후보" if spec and track != "엑셀 입력" else "파일 입력" if track == "엑셀 입력" else "소스 조사",
                "owner": "이정환: 출처 확인" if status == "출처 미기재" else "소스 조사·검증",
                "last_label": str(labels[-1]) if labels else "", "points": len(labels), "series_names": names,
                "axis_review": axis_issue, "legend_review": "범례 보완 필요" if legend_issue else "원자료 명칭 대조 전",
                "match_score_recorded": spec.get("_matchScore"), "match_verified": False,
                "source_checked_at": "", "notes": "", "fingerprint": digest,
            }
            decision = reviews.get(audit_key, {})
            allowed = {"release_frequency", "release_evidence_url", "confirmed_check_frequency", "update_mode", "owner", "source_checked_at", "notes", "match_verified", "source_status"}
            # Human decisions are retained only for the chart content reviewed.
            if decision and decision.get("fingerprint") == digest:
                row.update({k: v for k, v in decision.items() if k in allowed})
            elif decision:
                row["notes"] = "검토 이후 차트 변경: 기존 결정 재확인 필요"
            rows.append(row)
    id_counts = Counter(r["chart_id"] for r in rows if r["chart_id"])
    for row in rows:
        row["identity_review"] = "ID 없음" if not row["chart_id"] else "ID 중복 확인" if id_counts[row["chart_id"]] > 1 else "기존 ID"
    catalog = {}
    for row in rows:
        sid = row["source_id"]
        if sid:
            catalog.setdefault(sid, {"source_id": sid, "definition": row["source_definition"], "url": row["source_url"], "chart_keys": []})["chart_keys"].append(row["audit_key"])
    return {"generated_at": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
            "scope": "구조화된 차트 항목의 1차 점검; 원자료 실시간 대조 전. 이미지 전용 슬라이드 제외.",
            "complete_input": not errors, "input_errors": list({e["file"]: e for e in errors}.values()),
            "counts": {key: dict(Counter(r[key] for r in rows)) for key in ("source_status", "proposed_check_frequency", "axis_review", "legend_review", "identity_review")},
            "sources": list(catalog.values()), "charts": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args()
    errors = []
    review_path = args.output_dir / "source_reviews.json"
    reviews = read_json(review_path, errors) if review_path.exists() else {}
    if errors:
        raise SystemExit(f"검토 파일을 읽지 못했습니다: {errors}")
    report = build(args.data_dir, reviews)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    (args.output_dir / "source_inventory.json").write_text(payload + "\n", encoding="utf-8")
    template = (ROOT / "scripts" / "source_inventory.html").read_text(encoding="utf-8")
    (args.output_dir / "source_inventory.html").write_text(template.replace("__REPORT__", payload.replace("<", "\\u003c")), encoding="utf-8")
    print(json.dumps({"charts": len(report["charts"]), "sources": len(report["sources"]), "counts": report["counts"], "input_errors": report["input_errors"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

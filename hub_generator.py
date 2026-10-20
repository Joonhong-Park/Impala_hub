#!/usr/bin/env python3
"""
hub_generator.py — hub_links.yaml을 읽어 index.html을 생성한다.
사용: python3 hub_generator.py [--config hub_links.yaml] [--output index.html]
"""
from __future__ import annotations

import argparse
import html
import os
import sys
import tempfile
from datetime import datetime
from string import Template
from urllib.parse import urlparse

import yaml

# tag_styles에서 허용하는 스타일 이름 목록
ALLOWED_STYLES = {"primary", "secondary"}

DEFAULT_TITLE = "Impala Hub"
DEFAULT_SERVICE_ORDER: list[str] = [
    "Cloudera Manager",
    "Ranger",
    "Hue",
    "YARN ResourceManager",
    "Impala Coordinator (Refresh)",
    "Impala Coordinator (User)",
]

# ── 유틸 ────────────────────────────────────────────────────────────────────

def normalize(name: str) -> str:
    """서비스 이름 비교용 정규화: 소문자 + 앞뒤 공백 제거."""
    return name.strip().lower()


def e(text: str) -> str:
    """HTML 이스케이프 (속성값 포함)."""
    return html.escape(str(text), quote=True)


def parse_link(raw) -> dict:
    """링크 항목을 {url, label, tag} 딕셔너리로 변환."""
    if isinstance(raw, str):
        return {"url": raw, "label": None, "tag": None}
    return {
        "url": raw.get("url", ""),
        "label": raw.get("label") or None,
        "tag": raw.get("tag") or None,
    }


def default_label(url: str) -> str:
    """label이 없으면 호스트명의 첫 번째 점 앞 부분을 사용."""
    host = urlparse(url).hostname or url
    return host.split(".")[0]


def host_port(url: str) -> str:
    """host:port 표시용 문자열. 포트가 없으면 호스트만."""
    parsed = urlparse(url)
    if parsed.port:
        return f"{parsed.hostname}:{parsed.port}"
    return parsed.hostname or url


# ── 검증 ────────────────────────────────────────────────────────────────────

def validate(cfg: dict) -> None:
    """검증 실패 시 메시지를 출력하고 sys.exit(1)."""
    errors: list[str] = []
    warnings: list[str] = []

    tag_styles: dict[str, str] = cfg.get("tag_styles") or {}
    for tag, style in tag_styles.items():
        if style not in ALLOWED_STYLES:
            errors.append(
                f"tag_styles['{tag}']: 허용되지 않는 스타일 '{style}'. "
                f"허용 목록: {sorted(ALLOWED_STYLES)}"
            )

    service_order_raw: list[str] = cfg.get("service_order") or DEFAULT_SERVICE_ORDER
    required_norm = {normalize(s) for s in (cfg.get("required_services") or [])}

    all_urls: list[str] = []

    # common 검증
    common_service_names: set[str] = set()
    for item in cfg.get("common") or []:
        svc = item.get("service", "")
        if not svc:
            errors.append("common[]: service 키가 비어 있습니다.")
            continue
        norm = normalize(svc)
        if norm in common_service_names:
            errors.append(f"common: 서비스 이름 중복 — '{svc}'")
        common_service_names.add(norm)
        links = item.get("links") or []
        if not links:
            errors.append(f"common['{svc}']: links가 비어 있습니다.")
        for raw in links:
            lk = parse_link(raw)
            _validate_url(lk["url"], f"common['{svc}']", errors, warnings)
            if lk["url"]:
                all_urls.append(lk["url"])

    # clusters 검증
    clusters = cfg.get("clusters")
    if not clusters:
        errors.append("clusters가 비어 있거나 없습니다.")
    else:
        cluster_names: set[str] = set()
        seen_in_order: set[str] = set()

        for cl in clusters:
            cname = cl.get("name", "")
            if not cname:
                errors.append("clusters[]: name 키가 비어 있습니다.")
                continue
            if cname in cluster_names:
                errors.append(f"clusters: 클러스터 이름 중복 — '{cname}'")
            cluster_names.add(cname)

            svc_names_in_cluster: set[str] = set()
            for svc_item in cl.get("services") or []:
                svc = svc_item.get("service", "")
                if not svc:
                    errors.append(f"clusters['{cname}']: service 키가 비어 있습니다.")
                    continue
                norm = normalize(svc)
                if norm in svc_names_in_cluster:
                    errors.append(
                        f"clusters['{cname}']: 서비스 이름 중복 — '{svc}'"
                    )
                svc_names_in_cluster.add(norm)
                seen_in_order.add(norm)

                links = svc_item.get("links") or []
                if not links:
                    errors.append(
                        f"clusters['{cname}']['{svc}']: links가 비어 있습니다."
                    )
                for raw in links:
                    lk = parse_link(raw)
                    _validate_url(lk["url"], f"clusters['{cname}']['{svc}']", errors, warnings)
                    if lk["url"]:
                        all_urls.append(lk["url"])

            for req in required_norm:
                if req not in svc_names_in_cluster:
                    # required_services에서 원래 표기 찾기
                    orig = next(
                        s for s in (cfg.get("required_services") or [])
                        if normalize(s) == req
                    )
                    errors.append(
                        f"clusters['{cname}']: 필수 서비스 '{orig}'가 없습니다."
                    )

        # service_order 경고
        for raw_name in service_order_raw:
            norm = normalize(raw_name)
            if norm not in seen_in_order:
                warnings.append(
                    f"service_order에 '{raw_name}'이 있지만 어느 클러스터에도 없습니다. "
                    "오타 가능성을 확인하세요."
                )

    # URL 중복 경고
    seen_urls: set[str] = set()
    for url in all_urls:
        if url in seen_urls:
            warnings.append(f"URL 중복 — '{url}'. 복사·붙여넣기 실수일 수 있습니다.")
        seen_urls.add(url)

    for w in warnings:
        print(f"[경고] {w}", file=sys.stderr)
    if errors:
        for err in errors:
            print(f"[오류] {err}", file=sys.stderr)
        sys.exit(1)


def _validate_url(url: str, ctx: str, errors: list[str], warnings: list[str]) -> None:
    if not url:
        errors.append(f"{ctx}: URL이 비어 있습니다.")
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        errors.append(f"{ctx}: http/https가 아닙니다 — '{url}'")
    if parsed.scheme == "http":
        warnings.append(f"{ctx}: http 사용 중 — '{url}'")
    if not parsed.hostname:
        errors.append(f"{ctx}: 호스트가 없습니다 — '{url}'")


# ── 렌더링 헬퍼 ──────────────────────────────────────────────────────────────

def render_badge(tag: str | None, tag_styles: dict[str, str]) -> str:
    if not tag:
        return ""
    style_name = tag_styles.get(tag, "default")
    return f'<span class="badge badge-{e(style_name)}">{e(tag)}</span>'


def render_link_row(lk: dict, tag_styles: dict[str, str]) -> str:
    url = lk["url"]
    label = lk["label"] or default_label(url)
    hp = host_port(url)
    badge = render_badge(lk["tag"], tag_styles)
    return (
        f'<a class="link-row" href="{e(url)}" target="_blank" '
        f'rel="noopener noreferrer" title="{e(url)}">'
        f'{badge}<span class="link-label">{e(label)}</span>'
        f'<span class="link-host">{e(hp)}</span>'
        f"</a>"
    )


def render_cluster_link_row(lk: dict) -> str:
    url = lk["url"]
    return (
        f'<a class="link-row" href="{e(url)}" target="_blank" '
        f'rel="noopener noreferrer" title="{e(url)}">'
        f'<span class="link-url">{e(url)}</span>'
        f"</a>"
    )


def render_service_group(svc_name: str, links_raw: list) -> str:
    count = len(links_raw)
    rows = "\n".join(
        render_cluster_link_row(parse_link(r)) for r in links_raw
    )
    return (
        f'<div class="service-group">'
        f'<div class="service-title">{e(svc_name)}'
        f'<span class="link-count">{count}</span></div>'
        f"{rows}"
        f"</div>"
    )


def render_common_card(item: dict, tag_styles: dict) -> str:
    svc = item["service"]
    links_raw = item.get("links") or []
    rows = "\n".join(
        render_link_row(parse_link(r), tag_styles) for r in links_raw
    )
    # 링크 5개 이상이면 2열 표시
    links_class = "links-2col" if len(links_raw) >= 5 else "links-1col"
    return (
        f'<div class="common-card">'
        f'<div class="card-title">{e(svc)}</div>'
        f'<div class="{links_class}">{rows}</div>'
        f"</div>"
    )


def render_cluster_column(cl: dict, service_order_raw: list[str], tag_styles: dict) -> str:
    name = cl["name"]
    desc = cl.get("description") or ""
    services: list[dict] = cl.get("services") or []

    # service_order 순서대로 정렬
    norm_to_svc = {normalize(s["service"]): s for s in services}
    ordered: list[dict] = []
    seen_norm: set[str] = set()
    for so in service_order_raw:
        norm = normalize(so)
        if norm in norm_to_svc:
            ordered.append(norm_to_svc[norm])
            seen_norm.add(norm)
    # service_order에 없는 서비스는 YAML 순서대로 뒤에 추가
    for s in services:
        if normalize(s["service"]) not in seen_norm:
            ordered.append(s)

    groups = "\n".join(
        render_service_group(s["service"], s.get("links") or [])
        for s in ordered
    )
    desc_html = f'<div class="cluster-desc">{e(desc)}</div>' if desc else ""
    return (
        f'<div class="cluster-col">'
        f'<div class="cluster-head">'
        f'<div class="cluster-name">{e(name)}</div>'
        f"{desc_html}"
        f"</div>"
        f"{groups}"
        f"</div>"
    )


# ── HTML 생성 ────────────────────────────────────────────────────────────────

PAGE_TEMPLATE = Template("""\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<style>
/* 라이트 모드 고정: OS 다크 모드 무시 */
:root { color-scheme: only light; }
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 15px;
  line-height: 1.45;
  background: #f4f4f5;
  color: #18181b;
  padding: 12px 14px 28px;
}
a { color: inherit; text-decoration: none; }

/* 헤더 */
.page-header {
  font-size: 18px;
  font-weight: 700;
  color: #09090b;
  margin-bottom: 14px;
  letter-spacing: -.01em;
}

/* 영역 구분 라벨 */
.section-label {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: #a1a1aa;
  margin-bottom: 6px;
}

/* ── 공통 서비스 ── */
.common-section { margin-bottom: 14px; }
.common-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 6px;
}

.common-card {
  background: #fff;
  border: 1px solid #e4e4e7;
  border-radius: 5px;
  padding: 6px 8px 5px;
}
.card-title {
  font-size: 14px;
  font-weight: 700;
  color: #52525b;
  text-transform: uppercase;
  letter-spacing: .05em;
  margin-bottom: 3px;
  padding-bottom: 3px;
  border-bottom: 1px solid #e4e4e7;
}

/* ── 배지 ── */
.badge {
  display: inline-block;
  font-size: 11px;
  padding: 0 4px;
  border-radius: 3px;
  font-weight: 700;
  flex-shrink: 0;
  line-height: 15px;
  letter-spacing: .02em;
}
.badge-primary   { background: #dbeafe; color: #1d4ed8; }
.badge-secondary { background: #dcfce7; color: #15803d; }
.badge-default   { background: #f4f4f5; color: #52525b; }

.links-2col { display: grid; grid-template-columns: 1fr 1fr; }

/* ── 클러스터 그리드 ── */
.cluster-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 6px;
  align-items: start;
}
.cluster-col {
  background: #fff;
  border: 1px solid #e4e4e7;
  border-radius: 5px;
  overflow: hidden;
}
.cluster-head {
  padding: 6px 8px 5px;
  border-bottom: 2px solid #e4e4e7;
  background: #fafafa;
}
.cluster-name {
  font-size: 14px;
  font-weight: 700;
  color: #09090b;
  letter-spacing: -.01em;
}
.cluster-desc {
  font-size: 12px;
  color: #a1a1aa;
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── 서비스 그룹 ── */
.service-group {
  padding: 7px 8px 5px;
  border-bottom: 1px solid #d4d4d8;
}
.service-group:last-child { border-bottom: none; }

.service-title {
  font-size: 14px;
  font-weight: 700;
  color: #52525b;
  text-transform: uppercase;
  letter-spacing: .05em;
  padding: 2px 0 2px;
  display: flex;
  align-items: center;
  gap: 4px;
  border-bottom: 1px solid #e4e4e7;
  margin-bottom: 1px;
}
.link-count {
  font-size: 11px;
  color: #d4d4d8;
  font-weight: 500;
}

/* ── 링크 행 ── */
.link-row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 3px;
  border-radius: 3px;
  min-height: 24px;
  overflow: hidden;
}
.link-row:hover { background: #eff6ff; }
.link-row:active { background: #dbeafe; }

.link-label {
  flex-shrink: 0;
  font-size: 14px;
  font-weight: 500;
  color: #2563eb;
}
.link-url {
  font-size: 13px;
  color: #2563eb;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.link-host {
  font-size: 12px;
  color: #a1a1aa;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}

/* ── 푸터 ── */
.page-footer {
  margin-top: 16px;
  font-size: 12px;
  color: #d4d4d8;
  text-align: right;
}

/* ── 반응형 ── */
@media (max-width: 860px) {
  .cluster-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 600px) {
  .cluster-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 380px) {
  .cluster-grid { grid-template-columns: 1fr; }
}
</style>
</head>
<body>
<div class="page-header">$title</div>
$common_section
<div class="cluster-section">
<div class="section-label">Clusters</div>
<div class="cluster-grid">
$cluster_columns
</div>
</div>
<div class="page-footer">$footer</div>
</body>
</html>
""")


def build_html(cfg: dict, config_filename: str) -> str:
    title = e(cfg.get("title") or DEFAULT_TITLE)
    tag_styles: dict[str, str] = cfg.get("tag_styles") or {}
    service_order_raw: list[str] = cfg.get("service_order") or DEFAULT_SERVICE_ORDER
    common: list[dict] = cfg.get("common") or []
    clusters: list[dict] = cfg.get("clusters") or []

    # 공통 서비스 영역
    if common:
        cards = "\n".join(render_common_card(item, tag_styles) for item in common)
        common_section = (
            '<div class="common-section">'
            '<div class="section-label">Common Services</div>'
            f'<div class="common-cards">{cards}</div>'
            "</div>"
        )
    else:
        common_section = ""

    # 클러스터 컬럼
    cluster_columns = "\n".join(
        render_cluster_column(cl, service_order_raw, tag_styles) for cl in clusters
    )

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    footer = e(f"Generated {generated_at} from {config_filename}")

    return PAGE_TEMPLATE.substitute(
        title=title,
        common_section=common_section,
        cluster_columns=cluster_columns,
        footer=footer,
    )


# ── 진입점 ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="hub_links.yaml → index.html 생성기")
    parser.add_argument("--config", default="hub_links.yaml", metavar="FILE")
    parser.add_argument("--output", default="index.html", metavar="FILE")
    args = parser.parse_args()

    try:
        with open(args.config, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"[오류] 설정 파일을 찾을 수 없습니다: {args.config}", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as exc:
        print(f"[오류] YAML 파싱 실패: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(cfg, dict):
        print("[오류] YAML 최상위 값이 매핑(딕셔너리)이 아닙니다.", file=sys.stderr)
        sys.exit(1)

    validate(cfg)

    html_content = build_html(cfg, os.path.basename(args.config))

    # 원자적 쓰기: 임시 파일 → os.replace
    out_dir = os.path.dirname(os.path.abspath(args.output)) or "."
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=out_dir, delete=False, suffix=".tmp"
    ) as tmp:
        tmp.write(html_content)
        tmp_path = tmp.name

    try:
        os.replace(tmp_path, args.output)
    except Exception:
        os.unlink(tmp_path)
        raise

    print(f"생성 완료: {args.output}")


if __name__ == "__main__":
    main()

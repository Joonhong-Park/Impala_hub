# Impala Hub

Cloudera CDP 클러스터와 공통 서비스(Grafana, NiFi, Airflow 등)의 웹 UI 링크를 한 화면에 모아 보는 정적 허브 페이지.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `hub_links.yaml` | 클러스터·서비스·URL 정의 (유일한 수정 대상) |
| `hub_generator.py` | YAML 검증 후 `index.html` 생성 |
| `impala_hub.service` | systemd 서비스 파일 (python http.server, 포트 9292) |

## 설치

```bash
# 의존성
pip3 install pyyaml

# 파일 배포
mkdir -p /opt/impala_hub
cp hub_generator.py hub_links.yaml /opt/impala_hub/

# 서비스 등록
cp impala_hub.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now impala_hub
```

접속: `http://서버주소:9292`

## 사용 방법

1. `hub_links.yaml` 수정 (URL, 클러스터, 서비스 추가/삭제)
2. `python3 hub_generator.py` 실행
3. 브라우저 새로고침

검증 실패 시 기존 `index.html`은 그대로 유지됩니다.

## YAML 구조

```yaml
title: "페이지 제목"
service_order: [서비스 표시 순서]
required_services: [필수 서비스]
tag_styles:         # 배지 스타일: primary / secondary / warning / danger / info
  prod: primary
  dev: secondary

common:             # 클러스터와 무관한 공통 서비스
  - service: Grafana
    links:
      - url: https://grafana.example.com:3000
        label: 운영
        tag: prod

clusters:           # 클러스터 목록
  - name: CLUSTER-A
    description: 설명
    services:
      - service: Cloudera Manager
        links:
          - url: https://cm-a.example.com:7183
```

링크 항목은 URL 문자열 단독, 또는 `{url, label, tag}` 형태 모두 가능합니다.

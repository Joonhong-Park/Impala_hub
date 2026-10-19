# Impala Hub

Cloudera CDP 클러스터와 공통 서비스(Grafana, NiFi, Airflow 등)의 웹 UI 링크를 한 화면에 모아 보는 정적 허브 페이지.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `hub_links.yaml` | 클러스터·서비스·URL 정의 (유일한 수정 대상) |
| `hub_generator.py` | YAML 검증 후 `index.html` 생성 |
| `impala_hub.conf` | nginx 설정 파일 (포트 9292) |

## 설치

```bash
# 의존성
pip3 install pyyaml

# 파일 배포
mkdir -p /opt/impala_hub
cp hub_generator.py hub_links.yaml /opt/impala_hub/

# nginx 설정
cp impala_hub.conf /etc/nginx/conf.d/
nginx -t && systemctl reload nginx
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

service_order:          # 클러스터 컬럼 내 서비스 표시 순서
  - Cloudera Manager
  - Ranger

required_services:      # 모든 클러스터에 반드시 있어야 하는 서비스
  - Cloudera Manager

tag_styles:             # 배지 스타일 (허용값: primary, secondary)
  prod: primary         # 파란 배지
  dev: secondary        # 초록 배지

common:                 # 클러스터와 무관한 공통 서비스
  - service: Grafana
    links:
      - url: https://grafana.example.com:3000
        label: 운영
        tag: prod       # 배지 표시 (생략 가능)

clusters:               # 클러스터 목록 (YAML 순서 = 컬럼 순서)
  - name: CLUSTER-A
    description: 운영 클러스터 A
    services:
      - service: Cloudera Manager
        links:
          - url: https://cm-a.example.com:7183
            label: cm-a   # 생략 시 호스트명 앞부분 자동 사용
```

링크 항목은 URL 문자열 단독, 또는 `{url, label, tag}` 형태 모두 가능합니다.

## 화면 구성

- **Common Services**: 서비스별 카드 가로 배치. 링크 5개 이상인 카드는 내부 2열로 표시
- **Clusters**: 클러스터별 컬럼. 모든 컬럼에 동일한 서비스 순서 적용
- 화면 너비에 따라 컬럼 수 자동 조정 (860px→3열, 600px→2열, 380px→1열)

## 검증 항목

| 구분 | 내용 |
|---|---|
| 오류 (exit 1) | 클러스터/서비스 이름 중복, 빈 URL, 빈 links, 필수 서비스 누락, 허용되지 않는 tag 스타일 |
| 경고 (계속 진행) | http URL 사용, service_order에만 있고 클러스터에 없는 서비스, URL 중복 |

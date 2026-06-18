# PLAN — 구현 계획

전제: [PRD.md](PRD.md)의 요구사항, [BENCHMARK_EVERYTHING.md](BENCHMARK_EVERYTHING.md)의 설계 원칙(사전 색인 + 실시간 증분 갱신, 검색 시점엔 풀스캔 금지)을 따른다.

## 1. 전체 아키텍처

```
                ┌──────────────────────┐
   사용자 ──CLI──▶│   Query Engine        │── 결과(경로/스니펫/랭킹) ──▶ 사용자
                │  (FTS 검색 + 시맨틱)   │
                └─────────┬─────────────┘
                          │ 조회만 (풀스캔 없음)
                ┌─────────▼─────────────┐
                │   인덱스 저장소         │
                │  - FTS 인덱스 (전문)    │
                │  - 벡터 인덱스 (임베딩) │
                │  - 메타데이터(파일경로,  │
                │    mtime, hash 등)     │
                └─────────▲─────────────┘
                          │ 증분 갱신 (생성/수정/삭제/이동)
                ┌─────────┴─────────────┐
                │  Indexer / Watcher     │
                │  - 초기 풀스캔 (1회)    │
                │  - FSEvents 구독        │
                └────────────────────────┘
```

## 2. 기술 스택 제안

| 영역 | 선택 | 근거 |
|---|---|---|
| 언어 | Python 3.11+ | 파일시스템 워처, FTS, 임베딩 생태계가 모두 성숙. 개인 규모(수만 파일) 트래픽에서 성능 병목이 거의 인덱스/IO이지 언어 자체가 아님. CLI 배포는 `uv`/`pipx`로 단일 명령 설치 |
| 전문 검색 인덱스 | SQLite **FTS5** | 별도 서버 불필요(파일 1개), BM25 랭킹 내장, 트랜잭션으로 일관성 보장, Python 표준 `sqlite3`로 의존성 최소화 |
| 파일시스템 감시 (macOS) | `watchdog` 라이브러리 (내부적으로 FSEvents 사용) | FSEvents를 직접 바인딩하는 대신 성숙한 래퍼 사용, 추후 Linux(inotify) 백엔드도 동일 라이브러리로 커버 가능 → 이식성 확보 |
| 임베딩(시맨틱 검색) | 로컬 모델, 1차로 `sentence-transformers` (예: `all-MiniLM-L6-v2`) 또는 Ollama embedding 모델 중 Phase 3에서 벤치마크 후 결정 | 프라이버시(개인 메모 외부 전송 금지) + 오프라인 동작 요구 |
| 벡터 저장 | SQLite `sqlite-vec` 확장 (FTS5와 같은 DB 파일에 공존) | 별도 벡터DB 프로세스 없이 단일 인덱스 파일로 운영 단순화. 규모가 커지면 Phase 4에서 대안(Faiss 등) 검토 |
| CLI 프레임워크 | `typer` 또는 `argparse` | 가벼운 CLI, 서브커맨드(`index`, `watch`, `search`, `status`) 구성 용이 |

> 위 스택은 "1차 제안"이며 Phase 0 스파이크에서 실측 후 변경 가능(특히 임베딩 모델/런타임).

## 3. 데이터 모델 (초안)

```sql
-- 파일 메타데이터
CREATE TABLE files (
  id INTEGER PRIMARY KEY,
  path TEXT UNIQUE NOT NULL,
  mtime REAL NOT NULL,
  size INTEGER NOT NULL,
  content_hash TEXT NOT NULL
);

-- 전문 검색 인덱스 (FTS5, content는 files.id 와 매핑)
CREATE VIRTUAL TABLE files_fts USING fts5(
  path, body, content='', tokenize='unicode61'
);

-- 시맨틱 검색용 청크 + 임베딩
CREATE TABLE chunks (
  id INTEGER PRIMARY KEY,
  file_id INTEGER REFERENCES files(id),
  chunk_index INTEGER,
  text TEXT,
  embedding BLOB  -- sqlite-vec
);
```

## 4. 단계별 로드맵

### Phase 0 — 스파이크 / 기술 검증 ✅ 완료 (2026-06-17)
- [x] SQLite FTS5로 1만 개 텍스트 파일 색인 후 검색 응답시간 실측 → 색인 15.7s, 검색 평균 0.07ms.
- [x] `watchdog`(FSEvents) 이벤트 지연/누락 여부 실측 → 200건 연속, 평균 11.7ms/최대 14.3ms, 누락 0건.
  - **버그 발견 및 수정**: 심볼릭 링크를 resolve하지 않은 경로(`/var/...`)를 감시하면 FSEvents가 이벤트를 전혀 전달하지 않음. `.resolve()` 후 감시하도록 수정 (자세한 내용: [BENCHMARK_EVERYTHING.md](BENCHMARK_EVERYTHING.md) 5장). → **Phase 2 구현 시 사용자가 등록하는 폴더 경로는 반드시 resolve 후 watchdog에 전달**해야 함을 설계 요구사항으로 확정.
- [ ] 후보 임베딩 모델 2~3개로 색인 속도/검색 품질 비교 → **Phase 3로 연기**: `sentence-transformers` 등은 torch 의존성이 무거워(수백MB~GB) 스파이크 범위에서 제외, 모델 선정은 Phase 3 착수 시점에 별도로 진행.
- **출력물**: 실측 수치로 PRD 7~8장 보정 완료. 부산물로 `sbsearch.indexer`/`sbsearch.search` 핵심 로직이 이미 구현되어 Phase 1로 그대로 이어짐 (아래 참고).

### Phase 1 — 키워드 검색 MVP ✅ 완료 (2026-06-18)
- [x] FTS5 인덱서 (F2 핵심 로직): `sbsearch.indexer.index_directory`/`index_file`/`remove_file` — Phase 0 스파이크에서 선구현, 단위테스트 포함.
- [x] 검색 (F4 핵심 로직, F5): `sbsearch.search.search` — FTS5 MATCH 문법을 그대로 노출해 AND/OR/NOT/구문검색 지원, 단위테스트 포함.
- [x] 폴더 등록/제외 패턴 설정 (F1): `sbsearch.config`(JSON 영속화, root/exclude add·remove) + `sbsearch.excludes`(`pathspec` `gitignore` 매처) + `sbsearch.indexer.index_roots`(다중 루트 색인).
- [x] CLI 래핑 (F4, F7): `sbsearch.cli` — `root`/`exclude`/`index`/`search`/`status` 서브커맨드. `search`는 plain/json 출력, `--limit`, `-C`(FTS5 snippet 토큰 기준 컨텍스트) 지원.
- [x] `status` 명령 (F8): `sbsearch.status.get_status` — 색인 파일 수, 마지막 색인 파일의 mtime, 인덱스 파일 크기(WAL/SHM 포함).

### Phase 2 — 실시간 증분 색인
- FSEvents 구독 데몬(`watch` 서브커맨드 or launchd 등록) (F3).
- 생성/수정/삭제/이동 각각에 대한 인덱스 갱신 로직 + 멀티 이벤트 디바운싱.
- 비정상 종료 후 재시작 시 일관성 복구(파일 mtime/hash 비교로 누락분 재색인).

### Phase 3 — 시맨틱 검색
- 청크 분할 전략 결정(고정 길이 vs 문단 단위).
- 로컬 임베딩 모델 확정, 색인 시 청크 임베딩 생성·저장.
- `--semantic` 검색 모드: 쿼리 임베딩 → 벡터 유사도 검색 → 결과 병합/표시.

### Phase 4 — 다듬기 / 확장 (옵션)
- JSON 출력, 성능 튜닝(대용량 log 파일 스트리밍 파싱).
- 멀티플랫폼 어댑터 분리(Linux inotify 등) — 설계상 인터페이스만 미리 분리해두고 실제 구현은 필요 시.

## 5. 성능 전략 요약
- **색인 시점에 비용 집중**: 텍스트 읽기/토큰화/임베딩은 모두 색인 단계에서 끝낸다.
- **검색 시점은 인덱스 조회만**: FTS5 BM25 쿼리 + (옵션) 벡터 kNN 조회만 수행, 디스크 풀스캔 금지.
- **증분 갱신은 파일 단위로 국소화**: FSEvents 이벤트 1건 = 해당 파일 재색인 1건, 전체 재스캔 트리거 금지.

## 6. 리스크 및 대응
| 리스크 | 대응 |
|---|---|
| FSEvents 이벤트 누락(대량 변경 시) | 주기적(예: 1일 1회) 백그라운드 정합성 검사로 mtime/hash 불일치 파일 재색인 |
| ~~심볼릭 링크 경로(`/var/...`) 감시 시 FSEvents가 이벤트를 전달하지 않음~~ | **해결됨 (Phase 0)**: 감시 대상 경로는 항상 `.resolve()` 후 watchdog에 전달 |
| 대형 단일 log 파일(GB 단위) | Phase 4에서 스트리밍 파싱/부분 색인 검토, 1차는 일정 크기 이상 파일은 색인 제외 옵션 제공 |
| 임베딩 모델 성능/품질 트레이드오프 | Phase 0/3에서 실측 비교 후 결정, 모델 교체 가능하도록 추상화 |
| SQLite 동시 쓰기(검색 중 색인 갱신) | WAL 모드 사용으로 읽기/쓰기 동시성 확보 |

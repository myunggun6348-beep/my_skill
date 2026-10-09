# 공식·교내 기준 연결 방법

## 적용 우선순위

1. 대상 학년도 교육부 훈령과 학교생활기록부 기재요령
2. 교육청의 공식 안내와 질의 회신
3. 공식 범위 안에서 정한 학교 내부 기준
4. 사용자가 지정한 문체·분량 기준

충돌하면 상위 기준을 적용한다. 적용 학년도, 학교급, 학년, 영역, 입력 주체가 다르면 같은 규정을 자동 적용하지 않는다.

## 공식 파일을 붙이는 위치

이 스킬 폴더에 `references/official/` 폴더를 만들고 다음처럼 넣는다.

```text
references/
├─ official-guidance.md
├─ data-contract.md
├─ review-rules.md
└─ official/
   ├─ 2026-school-record-guidelines-highschool.pdf
   ├─ 2026-ministry-instruction-555.pdf
   └─ school-internal-guidelines.pdf
```

파일명은 달라도 된다. `SKILL.md`에서 이 폴더의 최신 자료를 먼저 읽도록 지시되어 있다. 공식 PDF 원문을 요약 파일로 대체하지 않는다.

## 2026학년도 공식 자료 위치

- 학교생활기록부 종합지원포털의 [2026학년도 학교생활기록부 기재요령 게시 안내](https://star.moe.go.kr/web/contents/m40100.do?id=107757&schM=view)
- 학교생활기록부 종합지원포털의 [학교생활기록 작성 및 관리지침(교육부훈령 제555호)](https://star.moe.go.kr/web/contents/m20103.do?id=108056&schM=view)
- 학교생활기록부 종합지원포털의 [2026학년도 고등학교 주요 개정사항](https://star.moe.go.kr/web/contents/m20900.do?id=107761&page=1&schM=view)

공식 포털의 파일이 개정되거나 대상 학년도가 바뀌면 새 원문을 붙이고 `assets/audit-config.json`의 `policy_year`와 영역별 상한을 함께 갱신한다.

## 사용 전 확인

- 대상 학년도와 설정 파일의 연도가 같은가?
- 기록 영역과 입력 담당자가 맞는가?
- 활동이 학교교육과정·학교교육계획의 기재 가능 범위에 있는가?
- 공식 금지사항과 학교 내부 추가 기준을 모두 반영했는가?
- 글자 수와 바이트 계산 방식이 학교 시스템의 안내와 같은가?

확정하지 못하면 자동 통과시키지 말고 `확인 필요`로 분류한다.

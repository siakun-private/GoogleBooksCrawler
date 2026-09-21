<!-- INTENT
페이지를 이미지로 저장하는 방식과 본문 구조를 보존하는 방식을 함께 유지합니다.
두 구현 모두 Python이므로 언어 대신 산출물과 수집 방식으로 구분합니다.
실행 환경과 중간 산출물은 각 크롤러 안에서 관리해 서로의 작업을 덮지 않도록 합니다.
-->
# Google Books Crawler

Google Play Books를 로컬에서 읽을 수 있게 저장하는 도구입니다. 페이지 이미지가 필요한 경우에는 `image-crawler`, 검색 가능한 본문과 EPUB이 필요한 경우에는 `epub-crawler`를 사용합니다.

| 작업 | 시작 문서 | 방식 |
| --- | --- | --- |
| 페이지 이미지 수집, 이미지 변환, PDF 생성 | [image-crawler](image-crawler/README.md) | Selenium과 별도 Chrome 세션 |
| 본문과 원본 이미지 보존, EPUB 생성, HTML 읽기 화면 | [epub-crawler](epub-crawler/README.md) | Orca에 로그인된 리더의 HTML 수집 |

새 세션은 [AGENTS.md](AGENTS.md)를 읽고 작업할 크롤러의 `AGENTS.md`로 이동합니다. EPUB 작업을 이어가려면 [인수인계 시작점](epub-crawler/docs/handoff.md)에서 저장된 산출물과 검증 상태를 먼저 확인합니다.

저장한 책은 [HTML 읽기 화면](epub-crawler/output/content/index.html)을 열면 됩니다. 이 링크의 대상과 EPUB은 로컬 산출물이므로 Git에는 포함하지 않습니다. 다른 컴퓨터로 옮길 때는 `epub-crawler/output`을 별도로 복사합니다.

저장소 라이선스는 루트의 [LICENSE](LICENSE)에서 확인합니다. 수집한 책, 이미지와 글꼴은 저장소 소스의 라이선스로 재허가되는 자료가 아닙니다.

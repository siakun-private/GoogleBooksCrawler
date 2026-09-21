<!-- INTENT
이미지와 PDF가 필요한 작업을 기존 GUI와 노트북으로 계속 실행하도록 안내합니다.
본문을 보존하는 EPUB 작업의 진입점과 구분하고, 설치 경로에 묶인 가상환경 대신 재생성 절차를 사용합니다.
-->
# Image Crawler

Google Play Books의 페이지 이미지를 Selenium으로 수집하고 PNG, JPEG와 PDF로 변환하는 기존 구현입니다. 검색 가능한 본문과 EPUB이 필요하면 [EPUB Crawler](../epub-crawler/README.md)를 사용합니다.

이 폴더에서 새 가상환경을 만들고 의존성을 설치합니다. Windows용 Python과 Chrome이 필요합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\run_gui.bat
```

`run_gui.bat`은 실행한 위치와 관계없이 이 폴더로 작업 디렉터리를 맞추며 `.venv`가 있으면 그 Python을 사용합니다. 없으면 PATH의 Python을 사용합니다. GUI만 직접 실행할 때도 이 폴더에서 `python gui_app.py`를 실행합니다. 기본 다운로드 경로와 Chrome 프로필, 설정 파일을 현재 작업 디렉터리에서 만들기 때문입니다.

예전 환경의 `Scripts`, `share`, `pyvenv.cfg`는 보존된 파일입니다. 이 경로를 활성화하거나 실행 파일 안의 절대 경로를 손으로 고치지 말고 `.venv`를 새로 만듭니다.

[운영 안내](docs/operations.md)에서 GUI와 노트북의 실행 순서를, [구조와 주의점](docs/architecture.md)에서 브라우저와 파일 처리의 제약을 확인합니다. 에이전트는 [AGENTS.md](AGENTS.md)를 먼저 읽습니다.

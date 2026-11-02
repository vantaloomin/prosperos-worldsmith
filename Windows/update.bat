@echo off
rem Updates Worldsmith: stops it if it is running, pulls the latest main from GitHub, then installs again
rem (Python packages and the built screen). Start it again with Windows\launch.bat.
setlocal
rem One block, so cmd has read all of it before git pull replaces this file.
(
    pushd "%~dp0.." || exit /b 1
    call "%~dp0stop.bat"
    git pull --ff-only || (
        echo.
        echo Updating did not finish: git could not pull. If you changed files here, commit or stash them first.
        popd
        exit /b 1
    )
    popd
    call "%~dp0install.bat" || exit /b 1
    echo.
    echo Worldsmith is up to date. Start it with Windows\launch.bat.
    exit /b 0
)

on run
  set targetUrl to "http://127.0.0.1:8912/mmar/apps/debate/debate.html"
  set jsPath to "/Users/sn/workspaces/mmar-l0-core/tmp_history_verify_8912.js"
  tell application "Google Chrome"
    activate
    if (count of windows) = 0 then make new window
    tell front window
      set foundTab to (make new tab at end of tabs with properties {URL:targetUrl})
      set active tab index to (count of tabs)
    end tell
    delay 2
    set jsSource to read POSIX file jsPath
    tell foundTab to execute javascript jsSource
    set waitCount to 0
    repeat while waitCount < 360
      delay 1
      tell foundTab to set stateJson to execute javascript "JSON.stringify(window.__mmarHistoryVerify || {})"
      if stateJson is not "" then
        if stateJson contains "\"done\":true" then exit repeat
      end if
      set waitCount to waitCount + 1
    end repeat
    tell foundTab to execute javascript "JSON.stringify(window.__mmarHistoryVerify || {})"
  end tell
end run

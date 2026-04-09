on run argv
  set targetUrl to "http://127.0.0.1:8787/mmar/apps/debate/debate.html"
  tell application "Safari"
    activate
    if (count of windows) = 0 then
      make new document
    end if
    tell front window
      set current tab to (make new tab with properties {URL:targetUrl})
    end tell
    delay 3
    do JavaScript "
      const q = (sel) => document.querySelector(sel);
      if (q('#archive-shell')) q('#archive-shell').hidden = true;
      if (q('#history-shell')) q('#history-shell').hidden = true;
      q('#run-debate')?.click();
      'started';
    " in current tab of front window
    set currentStatusJson to "{\"status\":\"\",\"runMeta\":\"\",\"turnCount\":0}"
    repeat with i from 1 to 60
      delay 5
      set currentStatusJson to do JavaScript "
        const q = (sel) => document.querySelector(sel);
        const turnCards = Array.from(document.querySelectorAll('#turn-log .turn-card'));
        const status = q('#run-status') ? q('#run-status').textContent.trim() : '';
        const runMeta = q('#run-meta') ? q('#run-meta').textContent.trim() : '';
        JSON.stringify({
          status,
          runMeta,
          turnCount: turnCards.length
        });
      " in current tab of front window
      if currentStatusJson contains "\"turnCount\":3" and currentStatusJson contains "Completed" then
        exit repeat
      end if
      if currentStatusJson contains "Live unavailable" or currentStatusJson contains "Blocked" then
        return currentStatusJson
      end if
    end repeat
    return do JavaScript "
      const q = (sel) => document.querySelector(sel);
      const cards = Array.from(document.querySelectorAll('#turn-log .turn-card')).map((card) => {
        const label = card.querySelector('.turn-card-label,.speaker-chip,.turn-label');
        return {
          label: label ? label.textContent.trim() : '',
          text: card.textContent.replace(/\\s+/g, ' ').trim()
        };
      });
      JSON.stringify({
        path: '/api/debate',
        mode: (q('#run-meta') && q('#run-meta').textContent.includes('Live')) ? 'live' : 'unknown',
        source: 'display',
        status: q('#run-status') ? q('#run-status').textContent.trim() : '',
        runMeta: q('#run-meta') ? q('#run-meta').textContent.trim() : '',
        cards
      });
    " in current tab of front window
  end tell
end run

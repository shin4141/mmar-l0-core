on run
  tell application "Safari"
    activate
    delay 1
    return do JavaScript "
      const q = (sel) => document.querySelector(sel);
      const detailLikeButton = q('#detail-like-button');
      const before = detailLikeButton ? detailLikeButton.textContent.trim() : '';
      const visible = !!detailLikeButton && !detailLikeButton.hidden;
      if (visible) detailLikeButton.click();
      JSON.stringify({
        topic: q('#topic-display') ? q('#topic-display').textContent.trim() : '',
        detailLikeVisible: visible,
        detailLikeBefore: before,
        detailLikeAfter: detailLikeButton ? detailLikeButton.textContent.trim() : '',
        archiveOpen: q('#archive-shell') ? !q('#archive-shell').hidden : false,
        listLikesText: [...document.querySelectorAll('#archive-panel .history-stats')][0]?.textContent?.trim() || ''
      });
    " in current tab of front window
  end tell
end run

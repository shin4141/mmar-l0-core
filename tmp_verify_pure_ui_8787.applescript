on run
	set targetUrl to "http://127.0.0.1:8787/mmar/apps/debate/debate.html"
	set runSpecs to {¬
		{"first_run", "宇宙人はこの銀河に存在するか", "存在しない", "存在する"}, ¬
		{"second_run", "AIは人間より良い意思決定ができるか", "できない", "できる"}, ¬
		{"third_run", "監視カメラは犯罪抑止に有効か", "有効ではない", "有効だ"}}
	tell application "Safari"
		activate
		open location targetUrl
		delay 3
	end tell
	my installErrorHooks()
	set resultsJson to "{"
	repeat with idx from 1 to count of runSpecs
		set spec to item idx of runSpecs
		set labelText to item 1 of spec
		set topicText to item 2 of spec
		set sideAText to item 3 of spec
		set sideBText to item 4 of spec
		set runJson to my executeRun(topicText, sideAText, sideBText)
		if idx > 1 then set resultsJson to resultsJson & ","
		set resultsJson to resultsJson & quote & labelText & quote & ":" & runJson
		if idx < count of runSpecs then my exitReaderMode()
	end repeat
	set resetJson to my collectReset()
	set resultsJson to resultsJson & ",\"reset\":" & resetJson & "}"
	return resultsJson
end run

on installErrorHooks()
	tell application "Safari"
		do JavaScript "
window.__codexErrors = [];
window.addEventListener('error', function(e) {
  window.__codexErrors.push({type: 'pageerror', text: String((e && e.message) || '')});
});
if (!window.__codexConsoleWrapped) {
  const orig = console.error.bind(console);
  console.error = function() {
    try { window.__codexErrors.push({type: 'console', text: Array.from(arguments).join(' ')}); } catch (e) {}
    return orig.apply(console, arguments);
  };
  window.__codexConsoleWrapped = true;
}" in document 1
	end tell
end installErrorHooks

on executeRun(topicText, sideAText, sideBText)
	tell application "Safari"
		do JavaScript "
document.querySelector('#topic').value = " & quoted form of topicText & ";
document.querySelector('#side-a').value = " & quoted form of sideAText & ";
document.querySelector('#side-b').value = " & quoted form of sideBText & ";
document.querySelector('#run-button').click();
" in document 1
	end tell
	repeat with i from 1 to 90
		delay 1
		tell application "Safari"
			set probe to do JavaScript "
(function () {
  const status = (document.querySelector('#status')?.textContent || '').trim();
  const cards = document.querySelectorAll('.turn-card').length;
  return JSON.stringify({status, cards});
})();" in document 1
		end tell
		if probe contains "\"status\":\"Debate complete\"" then exit repeat
		if probe contains "\"status\":\"Connection failed\"" then exit repeat
		if probe contains "\"status\":\"Debate failed\"" then exit repeat
	end repeat
	tell application "Safari"
		return do JavaScript "
(function () {
  const cards = Array.from(document.querySelectorAll('.turn-card')).map(el => (el.innerText || '').trim());
  return JSON.stringify({
    topicInput: (document.querySelector('#topic')?.value || '').trim(),
    topicDisplay: (document.querySelector('#topic-display')?.textContent || '').trim(),
    status: (document.querySelector('#status')?.textContent || '').trim(),
    turnCards: cards.length,
    turn1: cards[0] || '',
    turn2: cards[1] || '',
    turn3: cards[2] || '',
    errors: window.__codexErrors || []
  });
})();" in document 1
	end tell
end executeRun

on exitReaderMode()
	tell application "Safari"
		do JavaScript "
(function () {
  const back = document.querySelector('#reader-back-button');
  if (back && !back.hidden) back.click();
})();" in document 1
	end tell
	delay 1
end exitReaderMode

on collectReset()
	tell application "Safari"
		do JavaScript "
(function () {
  const next = document.querySelector('#reader-next-button');
  if (next && !next.hidden) next.click();
})();" in document 1
		delay 1
		return do JavaScript "
(function () {
  return JSON.stringify({
    topicEditable: !!(document.querySelector('#topic') && !document.querySelector('#topic').disabled),
    status: (document.querySelector('#status')?.textContent || '').trim(),
    turnCards: document.querySelectorAll('.turn-card').length,
    topicDisplay: (document.querySelector('#topic-display')?.textContent || '').trim(),
    errors: window.__codexErrors || []
  });
})();" in document 1
	end tell
end collectReset

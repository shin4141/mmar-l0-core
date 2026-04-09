on wait_for_ready(tabRef, timeoutSeconds)
	repeat with i from 1 to timeoutSeconds
		tell application "Safari"
			try
				if (do JavaScript "document.readyState" in tabRef) is "complete" then return true
			end try
		end tell
		delay 1
	end repeat
	return false
end wait_for_ready

on wait_for_status(tabRef, expectedText, timeoutSeconds)
	repeat with i from 1 to timeoutSeconds
		tell application "Safari"
			try
				set statusText to do JavaScript "document.querySelector('#status')?.textContent || ''" in tabRef
				if statusText contains expectedText then return statusText
			end try
		end tell
		delay 1
	end repeat
	return ""
end wait_for_status

on wait_for_topic_contains(tabRef, expectedText, timeoutSeconds)
	repeat with i from 1 to timeoutSeconds
		tell application "Safari"
			try
				set topicText to do JavaScript "document.querySelector('#topic-display')?.textContent || ''" in tabRef
				if topicText contains expectedText then return topicText
			end try
		end tell
		delay 1
	end repeat
	return ""
end wait_for_topic_contains

set pageUrl to "http://127.0.0.1:8931/debate.html"

tell application "Safari"
	activate
	if (count of windows) is 0 then make new document
	set current tab of front window to (make new tab with properties {URL:pageUrl})
	delay 2
	set tabRef to current tab of front window
end tell

if wait_for_ready(tabRef, 20) is false then error "page_not_ready"

tell application "Safari"
	do JavaScript "document.querySelector('#topic').value = '宇宙人は存在するか'; document.querySelector('#side-a').value = '存在しない'; document.querySelector('#side-b').value = '存在する'; document.querySelector('#keyword').value = ''; document.querySelector('#run-button').click();" in tabRef
end tell

set run1Status to wait_for_status(tabRef, "Debate", 120)

tell application "Safari"
	set run1Topic to do JavaScript "document.querySelector('#topic-display')?.textContent || ''" in tabRef
	set swapResult to do JavaScript "document.querySelector('#side-a').value = 'A side'; document.querySelector('#side-b').value = 'B side'; document.querySelector('#swap-sides-button').click(); JSON.stringify({a: document.querySelector('#side-a').value, b: document.querySelector('#side-b').value});" in tabRef
	do JavaScript "document.querySelector('#topic').value = '宇宙人は存在するか'; document.querySelector('#side-a').value = '存在しない'; document.querySelector('#side-b').value = '存在する'; document.querySelector('#keyword').value = 'ETH'; document.querySelector('#run-button').click();" in tabRef
end tell

set run2Status to wait_for_status(tabRef, "Debate", 120)
set topicWithKeyword to wait_for_topic_contains(tabRef, "(ETH)", 20)

tell application "Safari"
	do JavaScript "document.querySelector('#save-button')?.click();" in tabRef
end tell

delay 3

tell application "Safari"
	do JavaScript "const btn = document.querySelector('[data-record-id]'); if (btn) btn.click();" in tabRef
end tell

delay 3

tell application "Safari"
	set restoredKeyword to do JavaScript "document.querySelector('#keyword')?.value || ''" in tabRef
	set finalJson to do JavaScript "JSON.stringify({run1Status: document.querySelector('#status')?.textContent || '', run1Topic: document.querySelector('#topic-display')?.textContent || '', swapResult: " & swapResult & ", run2Status: document.querySelector('#status')?.textContent || '', topicWithKeyword: document.querySelector('#topic-display')?.textContent || '', restoredKeyword: document.querySelector('#keyword')?.value || ''})" in tabRef
	log finalJson
end tell

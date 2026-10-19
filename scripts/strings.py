"""What the scripts say to the user, in each language Vinutes speaks (see i18n.py). Both tables have the same keys
and the same {blanks}; tests/test_app.py checks that. The zh-TW words are the ones Vinutes has always used.

Only words that reach the user live here: messages the window or the menu shows, the activity log, labels on the
page. File names, prompts for the AI and text written into the minutes, the glossary or notes.md stay in the scripts.
A literal brace would be {{ or }} (the words go through str.format).
"""

EN = {
    # shared
    'speaker': 'Speaker',
    'you': 'You',
    'someone': 'Someone',
    'assistant': 'Assistant',
    'list_sep': ', ',
    'quote': '“{text}”',
    'timeout': 'The connection timed out. Please try again later.',
    'unexpected': 'Something unexpected went wrong ({err}).',
    'ai_missing': "Can't find {ai}. Install it and sign in at item 5 of the Setup Checklist.",

    # ai_runner.py
    'ai_unknown': "There's no AI by that name.",
    'ai_install_failed': "{ai} couldn't be installed.",
    'ai_bad_settings': "settings.json isn't in the right format, so the AI can't be changed.",

    # references.py
    'ref_no_file': "{name} can't be found. It may have been moved or deleted.",
    'ref_kind': "{name} can't be read. Files for the AI can be PDF, Word, Excel, PowerPoint, text or pictures.",
    'ref_unreadable': "{name} couldn't be opened. Save it again as a PDF and add it once more.",
    'ref_link_failed': "This link couldn't be opened: {url}. Check the address, or save the page as a file and add "
                       'that instead.',
    'ref_link_login': 'This link needs a sign-in, so the AI cannot read it: {url}. Save the page as a file and add '
                      'that instead.',
    'ref_link_kind': "This link isn't a web page or a PDF, so it can't be read: {url}",
    'ref_google_right': "Your Google account can't open this file: {url}",
    'ref_link_big': "This link's file is over 20 MB, too big for the AI to read: {url}",
    'ref_cut': '[The rest of this file was left out: it is too long.]',

    # attachments.py
    'attach_no_items': 'There are no files, links or pictures to add.',
    'attach_no_doc': "This meeting isn't in Google Docs yet. Files and pictures can be added once the minutes are "
                     'published to Google Docs.',
    'attach_offline': "Not connected to Google, so the files and pictures couldn't be saved to Google Drive. Section 8 "
                      "hasn't changed. Try again once you're online.",
    'attach_no_public': "The picture can't show inside the Google Doc because your Google account doesn't allow "
                        'sharing files by link. The picture is saved in Google Drive, and section 8 has a link to it.',
    'attach_login': "Your Google sign-in has expired, so the files weren't saved to Google Drive and section 8 hasn't "
                    'changed. Sign in again at item 7 of the Setup Checklist.',
    'attach_no_right': "Your Google account can't save files in the folder this Google Doc is in, so section 8 hasn't "
                       'changed.',
    'attach_failed': "The files couldn't be saved to Google Drive, so section 8 hasn't changed. Please try again.",
    'attach_crowded': "A colleague was editing the Google Doc at the same moment, so these files and links weren't "
                      'added to section 8. The files are saved in Google Drive; please add them again.',
    'attach_no_line': "Section 8 has no line for “{name}”, so this picture wasn't put into the Google Doc.",
    'attach_not_placed': "The picture “{name}” couldn't go into the Google Doc, so section 8 has a link to it instead.",
    'attach_no_file': "Can't find this file: {name}.",
    'attach_no_name': '(no file name)',
    'attach_bad_url': 'Links must start with http:// or https://.',
    'attach_not_picture': "“{name}” isn't a picture. Add it with “Upload a file” instead.",
    'attach_cant_convert': "“{name}” couldn't be turned into a picture format Google Docs can show.",

    # doc_sync.py
    'busy': 'A colleague is editing the Google Doc right now. Your changes are kept on this computer and will be '
            'saved back the next time you save.',

    # auto_minutes.py: known failures, in words the user can act on
    'err_login_expired': 'Your Google sign-in has expired. Sign in again at item 7 of the Setup Checklist.',
    'err_no_google': "This computer hasn't finished the Google setup. Set it up at items 6 and 7 of the Setup "
                     'Checklist.',
    'err_already_mailed': 'These minutes were already emailed to some of these recipients.',
    'err_plain_addresses': 'Recipients can only be email addresses, like name@example.com, without names.',
    'err_not_installed': "The transcription package isn't installed properly. Run recorder/install.sh again.",
    'err_cannot_read_audio': "The recording can't be read. The recording may have been interrupted.",
    'err_doc_changed': 'Someone has already edited the Google Doc. Please make your changes in Google Docs.',
    'err_open_comments': 'The Google Doc has comments nobody has dealt with yet. Please make your changes in Google '
                         'Docs.',
    'err_docs_api': "The Google Docs API isn't turned on in your Google Cloud project yet. Click “Turn on” at item 8 of "
                    'the Setup Checklist.',
    'err_rate_limit': '{ai} has used up its usage limit. Click “Write up again” once it resets.',
    'err_limit_until': '{ai} has used up its usage limit until {when}. You can switch to another AI meanwhile.',
    'people_no_name': 'Type a name first.',
    'log_people_add': 'Added {name} to the attendees',
    'log_people_remove': 'Took {name} off the attendees',
    'err_codex_old': "Codex is too old to work with a ChatGPT account. Update Codex, then click “Write up again”.",
    'err_not_logged_in': "{ai} isn't signed in. Sign in at item 5 of the Setup Checklist.",
    # auto_minutes.py: the write-up
    'no_audio': "Can't find the recording file.",
    'log_started': 'Started recording',
    'log_ended': 'Stopped recording, {length} long',
    'status_transcribing': 'Turning the recording into a transcript',
    'transcribe_timeout': "The transcript still wasn't done after 4 hours, so it was stopped.",
    'transcribe_failed': "Couldn't turn the recording into a transcript.",
    'no_speech': 'No speech was heard in the recording. Check that the microphone picks up sound while you record.',
    'log_transcribed': 'Turned the recording into a transcript',
    'status_speakers': 'Working out who said each line',
    'write_timeout': "The minutes still weren't done after {n} minutes, so the write-up was stopped. The transcript is "
                     "still in the recording's folder.",
    'write_error': '{ai} ran into a problem writing the minutes.',
    'not_finished_retry': "The minutes weren't finished. The transcript is still in the recording's folder; click "
                          '“Write up again” to try again.',
    'not_finished': "The minutes weren't finished.",
    'no_minutes_file': "The minutes file wasn't there after the write-up.",
    'leaks': 'The minutes {ai} wrote contain text that looks like sign-in details, so to be safe they weren\'t '
             "published to Google Docs. The transcript is still in the recording's folder; click “Write up again” to "
             'try again.',
    'untitled_minutes': 'Meeting Minutes',
    'publish_failed': 'The minutes are written, but publishing them to Google Docs failed.',
    'status_writing': 'Writing the minutes',
    'log_published': 'Wrote the minutes and published them to Google Docs',
    'unexpected_run': "Something unexpected went wrong while writing the minutes. The recording and the transcript are "
                      "still in the recording's folder.",
    # auto_minutes.py: the mail
    'attachment_gone': 'The attachment is missing. Click “Send email” again.',
    'no_word': "Couldn't make the Word file.",
    'no_pdf': "Couldn't make the PDF file.",
    'word_offline': "Not connected to Google Docs, so the Word file couldn't be made from the latest version. The "
                    "email wasn't sent.",
    'mail_sending': 'This email is being sent. Please wait.',
    'mail_attach_slow': "The previous attachment still wasn't ready after 5 minutes, so the email wasn't sent. Please "
                        'try again later.',
    'mail_already_sent': 'This email was already sent on {at}.',
    'mail_none': "These minutes don't have an email ready.",
    'mail_preview_failed': "Couldn't preview the email, so it wasn't sent.",
    'mail_changed': 'The email changed after the preview. Click “Send email” again.',
    'mail_not_sent': "The email wasn't sent.",
    'log_sent': 'Sent to {names} as a {format}',

    # minutes_app.py: words for dates, lengths and formats
    'weekdays': 'Mon,Tue,Wed,Thu,Fri,Sat,Sun',
    'months': 'Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec',
    'day_label': '{weekday}, {month} {day}',
    'day_label_year': '{weekday}, {month} {day}, {year}',
    'short_time': '{month} {day} {time}',
    'len_min': '{m} min',
    'len_hour': '{h} h',
    'fmt_word': 'Word file',
    'fmt_pdf': 'PDF file',
    'fmt_gdoc': 'Google Docs link',
    # minutes_app.py: messages
    'job_missing': "Can't find this recording.",
    'no_file': "The minutes file for this meeting isn't on this computer, so it can't be edited right now.",
    'update_not_git': "Vinutes wasn't installed with git clone, so it can't update itself. Please install it again "
                      'following the README.',
    'update_no_network': "Couldn't download the new version. Check your internet connection, then click “Update” "
                         'again.',
    'update_failed': "Couldn't download the new version. The network may be down, or someone changed files in the "
                     'Vinutes folder. If the network is fine and it still fails, please install it again following '
                     'the README.',
    'edited_by': '{who} edited this in Google Docs',
    'offline_saved': 'Not connected to Google Docs. Your changes are kept on this computer and will be saved back the '
                     'next time you save or open this meeting.',
    'no_docs_api': "This computer's Google connection doesn't have the Google Docs API turned on yet. Your changes are "
                   'kept on this computer. Click “Turn on” at item 8 of the Setup Checklist to fix it.',
    'login_saved': 'Your Google sign-in has expired. Your changes are kept on this computer and will be saved back '
                   'the next time you save, after you sign in again at item 7 of the Setup Checklist.',
    'no_right_saved': "Your Google account can't edit this Google Doc. Your changes are kept on this computer and will "
                      'be saved back the next time you save, once the owner gives you edit access.',
    'gone_saved': "Can't find this Google Doc; it may have been deleted. Your changes are kept in the minutes file on "
                  'this computer.',
    'offline_open': "Not connected to Google Docs. You're seeing the version on this computer.",
    'login_open': "Your Google sign-in has expired. You're seeing the version on this computer. Sign in again at "
                  'item 7 of the Setup Checklist.',
    'no_right_open': "Your Google account can't open this Google Doc. You're seeing the version on this computer.",
    'gone_open': "Can't find this Google Doc; it may have been deleted. You're seeing the version on this computer.",
    'offline_conflict': 'A colleague also changed some paragraphs you edited while offline, so these keep your '
                        "colleague's version: ",
    'offline_spare': '. Your offline version is kept separately as “{name}”.',
    'not_applied': "These paragraphs you hadn't saved back couldn't be applied to the Google Doc's version. Please "
                   'change them again: ',
    'tables_changed': 'Someone changed the number of table rows in the Google Doc, so the minutes now match the Google '
                      'Doc.',
    'table_shape': "Table rows and columns can't be added or removed here, so this change wasn't saved. To add or "
                   'remove rows or columns, edit the Google Doc.',
    'ai_tables_offline': "{ai}'s change adds or removes table rows or columns, which can only be saved while connected "
                         "to Google Docs. The minutes haven't changed.",
    'ai_tables_comments': "{ai}'s change adds or removes table rows or columns, so the whole document has to be uploaded "
                          'again. The Google Doc still has open comments, which would no longer point at their text '
                          "after that, so the minutes haven't changed. Deal with the comments, then try again.",
    'ai_tables_colleague': "A colleague edited the Google Doc while {ai} was making its change, so {ai}'s change wasn't "
                           'saved. Try again and {ai} will start from the latest version.',
    'whole_comments': "Someone just commented in the Google Doc, so this change to the tables wasn't saved back, and "
                      'the minutes now match the Google Doc.',
    'whole_colleague': "A colleague was editing the Google Doc at the same time, so this change to the tables wasn't "
                       'saved back, and the minutes now match the Google Doc.',
    'rejected_saved': "Google Docs didn't accept this change. Your changes are kept on this computer. Open this meeting "
                      "again and retry; if it still doesn't work, please edit the Google Doc.",
    'rejected_open': "Google Docs didn't accept the changes on this computer that weren't saved back yet. You're "
                     'seeing the version on this computer.',
    'gs_login': 'Your Google sign-in has expired, so {what}. Sign in again at item 7 of the Setup Checklist.',
    'gs_offline': 'Not connected to Google, so {what}. Please try again.',
    'gs_other': '{what}. Please try again.',
    'reply_not_sent': "your reply wasn't sent",
    'resolve_not_done': "the comment wasn't marked as resolved",
    'delete_not_done': "the meeting wasn't deleted",
    'not_as_planned': "After saving to Google Docs, a few paragraphs didn't come out as expected, so the preview now "
                      "shows the Google Doc's version.",
    'unsaved_spare': " Your changes that weren't saved back are kept separately in “{name}”; compare them and make "
                     'the changes again.',
    'change_spare': ' This change is kept separately in “{name}”.',
    'busy_meeting': 'Something else is still running for this meeting. Please try again shortly.',
    'not_ready': "This meeting's minutes aren't ready yet, so they can't be edited.",
    'bad_tags': "The tags weren't saved. Please try again.",
    'bad_project': "The project name can't be empty.",
    'bad_brief': "The brief didn't come through. Try again.",
    'item_missing': "Can't find this item.",
    'check_missing': "Can't find this item.",
    'reply_empty': 'The reply is empty.',
    'undo_nothing': "There's no change to undo.",
    'undo_tables': "{ai} changed the number of table rows, so only its own changes can't be undone. To change them "
                   'back, please edit the Google Doc.',
    'ai_timeout': "{ai} still wasn't done after 10 minutes, so it was stopped. The minutes haven't changed.",
    'ai_error': "{ai} ran into a problem making the change. The minutes haven't changed.",
    'ai_nothing': 'Nothing in the minutes needed changing',
    'ai_broken': "The minutes {ai} returned were incomplete, so they weren't saved.",
    'ai_leaks': "The minutes {ai} returned contain text that looks like sign-in details, so to be safe they weren't "
                'saved.',
    'ai_done': 'Changed as you asked',
    'ai_saved_doc': ', and saved to Google Docs',
    'missing_file': "The minutes file “{name}” for this meeting isn't on this computer; it may have been moved or "
                    'renamed.',
    'missing_showing_doc': " You're seeing the Google Doc.",
    'missing_put_back': ' To edit it here, put the minutes file back in “{folder}”.',
    'reply_attached': 'Added to section 8, Supporting Materials: {names}',
    # minutes_app.py: the quick buttons, as the activity log names them
    'quick_short': 'Shorter',
    'quick_detail': 'More detail',
    'quick_formal': 'More formal',
    'quick_visual': 'Use tables',
    'quick_external': 'External version',
    # minutes_app.py: the activity log
    'where_doc': ' in Google Docs',
    'where_preview': ' in the preview',
    'chg_add': 'Added a paragraph{where}: “{text}”',
    'chg_remove': 'Deleted a paragraph{where}: “{text}”',
    'chg_fill': 'Added “{text}”{where}',
    'chg_delete': 'Deleted “{text}”{where}',
    'chg_change': 'Changed “{before}” to “{after}”{where}',
    'log_more_doc_edits': 'Made {n} more changes in Google Docs',
    'log_table_rows': 'Changed the number of table rows in Google Docs',
    'log_changed_after_send': 'Changed the minutes after sending; the {format} that was sent is still the earlier '
                              'version',
    'log_comment': 'Commented in Google Docs: “{text}”',
    'log_resolved': 'Marked {who}’s comment as resolved',
    'log_resolved_own': 'Marked your own comment as resolved',
    'log_resolved_anon': 'Marked a comment as resolved',
    'log_replied': 'Replied to {who}’s comment: “{text}”',
    'log_replied_own': 'Replied to your own comment: “{text}”',
    'log_replied_anon': 'Replied to a comment: “{text}”',
    'bounce_no_address': "; the address doesn't exist",
    'log_bounce': "Email bounced: the email to {names} didn't arrive{why}",
    'log_learned_term': 'Added to the glossary: {text}',
    'log_learned_brief': 'Added to the {project} brief: {text}',
    'log_brief_person': 'Added {name} to the {project} brief',
    'new_person_label': 'New name: {name}',
    'log_learned_pref': 'Added to your preferences: {text}',
    'log_unlearn': "Won't remember: {text}",
    'log_relearn': 'Will remember again: {text}',
    'log_tables_not_saved': "This change to the table rows or columns wasn't saved to Google Docs",
    'log_attached': 'Added {names} to section 8, Supporting Materials',
    'log_noted': 'Added to section 8, Supporting Materials: “{text}”',
    'log_replaced': 'Changed “{old}” to “{new}”',
    'note_empty': 'There is nothing to add.',
    'replace_missing': "The minutes don't have that text. Copy it exactly as get_minutes gives it, with the marks for bold and links; someone may also have changed it already.",
    'replace_lines': 'Change one line at a time: the old and the new text must not contain line breaks.',
    'replace_many': 'That text appears {n} times in the minutes. Include more of the words around it, so it matches one place only.',
    'log_quick': 'Rewrote the minutes: {label}',
    'log_asked': 'Made the requested change: “{text}”',
    'log_undo': "Undid {ai}'s last change",
    'log_confirmed': 'Looks right: {label}',
    'log_skipped': 'Skipped: {label}',
    'log_corrected': 'Fixed: {label}, now “{right}”',
    'correct_empty': 'Type what it should be first.',
    'speaker_line_at': 'the line at {at}',
    'speaker_a_line': 'a line',
    'log_speaker': 'Marked {what} as {who}',
    'log_voice_off': 'Removed {who}',
    'log_voice_back': 'Put back {who}',
    # minutes_app.py: what was learned from the user's edits
    'lesson_fill': 'Added “{text}”',
    'lesson_delete': 'Deleted “{text}”',
    'lesson_term': 'From now on, write “{before}” as “{after}”',
    'lesson_pref': 'From now on, leave out “{before}”',
    'lesson_style': 'Your wording: “{text}”',
    'lesson_change': '“{before}” changed to “{after}”',

    # speakers.py
    'speakers_no_input': "There's no transcript or recording, so the speakers can't be told apart.",
    'speakers_none': "Speakers haven't been told apart for this meeting yet, so they can't be named.",
    'speaker_missing': "Can't find this speaker.",
    'line_missing': "Can't find this line.",

    # setup_check.py
    'client_not_google': "This isn't a Google client file. Choose the JSON file you downloaded from Google Cloud.",
    'client_web': 'This is a “Web application” client. Create a “Desktop app” client instead and download it again.',
}

ZH = {
    # shared
    'speaker': '講者',
    'you': '你',
    'someone': '有人',
    'assistant': '助手',
    'list_sep': '、',
    'quote': '「{text}」',
    'timeout': '連線逾時，請稍後再試一次。',
    'unexpected': '發生沒有預期的錯誤（{err}）。',
    'ai_missing': '找不到 {ai}。請到「環境設定自檢」的第 5 項安裝並登入。',

    # ai_runner.py
    'ai_unknown': '沒有這個 AI。',
    'ai_install_failed': '{ai} 安裝失敗',
    'ai_bad_settings': 'settings.json 的格式不對，沒辦法換 AI。',

    # references.py
    'ref_no_file': '找不到「{name}」，可能已經移走或刪除。',
    'ref_kind': '「{name}」這種檔案沒辦法讀取。給 AI 參考的檔案可以是 PDF、Word、Excel、PowerPoint、文字檔或圖片。',
    'ref_unreadable': '「{name}」打不開，請另存成 PDF 再放一次。',
    'ref_link_failed': '這個網址打不開：{url}。請確認網址，或把網頁存成檔案再放上來。',
    'ref_link_login': '這個網址要登入才能看，AI 沒辦法讀取：{url}。請把網頁存成檔案再放上來。',
    'ref_link_kind': '這個網址不是網頁也不是 PDF，沒辦法讀取：{url}',
    'ref_google_right': '你的 Google 帳號沒有這份檔案的權限：{url}',
    'ref_link_big': '這個網址的檔案超過 20 MB，AI 沒辦法讀取：{url}',
    'ref_cut': '[The rest of this file was left out: it is too long.]',

    # attachments.py
    'attach_no_items': '沒有要加進去的檔案、連結或圖片。',
    'attach_no_doc': '這場會議還沒有 Google 文件，附件和圖片要等會議記錄發成 Google 文件之後才能加。',
    'attach_offline': '沒有連上 Google，檔案和圖片沒辦法存進雲端硬碟，第八章沒有變動。連上網路之後再試一次。',
    'attach_no_public': ('圖片沒辦法直接顯示在 Google 文件裡，因為你的 Google 帳號不允許用連結分享檔案。'
                         '圖片已經存進雲端硬碟，第八章放的是圖片的連結。'),
    'attach_login': 'Google 登入已經失效，檔案沒有存進雲端硬碟，第八章沒有變動。請到「環境設定自檢」的第 7 項重新登入。',
    'attach_no_right': '你的 Google 帳號沒有權限把檔案存進這份文件所在的資料夾，第八章沒有變動。',
    'attach_failed': '檔案沒辦法存進雲端硬碟，第八章沒有變動。請再試一次。',
    'attach_crowded': '同事剛好也在修改 Google 文件，這次的檔案和連結沒有加進第八章。檔案已經存進雲端硬碟，請再加一次。',
    'attach_no_line': '第八章找不到「{name}」這一行，這張圖片沒有放進 Google 文件。',
    'attach_not_placed': '圖片「{name}」沒辦法放進 Google 文件，第八章放的是這張圖片的連結。',
    'attach_no_file': '找不到這個檔案：{name}。',
    'attach_no_name': '（沒有檔名）',
    'attach_bad_url': '網址要用 http:// 或 https:// 開頭。',
    'attach_not_picture': '「{name}」不是圖片，請改用「上傳檔案」加進去。',
    'attach_cant_convert': '「{name}」沒辦法轉成 Google 文件能顯示的圖片格式。',

    # doc_sync.py
    'busy': '同事正在 Google 文件上修改，你改的內容先存在這台電腦，下次存檔時會一起存回。',

    # auto_minutes.py: known failures, in words the user can act on
    'err_login_expired': 'Google 登入已經失效，請到「環境設定自檢」的第 7 項重新登入。',
    'err_no_google': '這台電腦還沒有完成 Google 設定，請照「環境設定自檢」的第 6、7 項設定。',
    'err_already_mailed': '這份紀錄已經寄給其中幾位收件人了。',
    'err_plain_addresses': '收件人只能寫信箱，例如 name@example.com，不能加名字。',
    'err_not_installed': '轉逐字稿的套件沒有裝好，請重新執行 recorder/install.sh。',
    'err_cannot_read_audio': '錄音檔讀不出來，可能是錄音過程被中斷。',
    'err_doc_changed': '有人已經在 Google 文件上改過，請直接到 Google 文件修改。',
    'err_open_comments': 'Google 文件上有還沒處理的留言，請直接到 Google 文件修改。',
    'err_docs_api': 'Google Cloud 專案還沒開啟 Google Docs API，請到「環境設定自檢」的第 8 項按「開啟」。',
    'err_rate_limit': '{ai} 的用量已經用完，等額度恢復後再按「重新整理」。',
    'err_limit_until': '{ai} 的用量已經用完，{when}才會恢復，可以先換用其他 AI。',
    'people_no_name': '請先輸入名字。',
    'log_people_add': '把 {name} 加進與會人員',
    'log_people_remove': '把 {name} 從與會人員移除',
    'err_codex_old': 'Codex 的版本太舊，沒辦法用 ChatGPT 帳號整理。請先更新 Codex，再按「重新整理」。',
    'err_not_logged_in': '{ai} 還沒登入，請到「環境設定自檢」的第 5 項登入。',
    # auto_minutes.py: the write-up
    'no_audio': '找不到錄音檔。',
    'log_started': '開始錄音',
    'log_ended': '結束錄音，長度 {length}',
    'status_transcribing': '正在把錄音轉成逐字稿',
    'transcribe_timeout': '轉逐字稿超過 4 小時還沒完成，已經停止。',
    'transcribe_failed': '錄音轉逐字稿失敗。',
    'no_speech': '錄音裡沒有聽到說話的聲音。請確認錄音時麥克風有收到聲音。',
    'log_transcribed': '把錄音轉成逐字稿',
    'status_speakers': '正在分辨每一句的講者',
    'write_timeout': '整理超過 {n} 分鐘還沒完成，已經停止。逐字稿留在錄音資料夾裡。',
    'write_error': '{ai} 整理時出錯。',
    'not_finished_retry': '整理沒有完成。逐字稿留在錄音資料夾裡，可以按「重新整理」再試一次。',
    'not_finished': '整理沒有完成。',
    'no_minutes_file': '整理完沒有找到會議紀錄檔。',
    'leaks': ('{ai} 寫出來的紀錄裡有看起來像登入資料的文字，為了安全，這份紀錄沒有發成 Google 文件。'
              '逐字稿留在錄音資料夾裡，可以按「重新整理」再試一次。'),
    'untitled_minutes': '會議紀錄',
    'publish_failed': '會議紀錄寫好了，發成 Google 文件時失敗。',
    'status_writing': '正在整理成會議紀錄',
    'log_published': '整理完會議記錄，發成 Google 文件',
    'unexpected_run': '整理時發生沒有預期的錯誤。錄音和逐字稿都還在錄音資料夾裡。',
    # auto_minutes.py: the mail
    'attachment_gone': '附件不見了，請重新按寄出。',
    'no_word': '沒辦法產生 Word 檔。',
    'no_pdf': '沒辦法產生 PDF 檔。',
    'word_offline': '沒有連上 Google 文件，沒辦法用最新的內容產生 Word 檔，信沒有寄出。',
    'mail_sending': '這封信正在寄出，請稍等。',
    'mail_attach_slow': '前一個附件準備超過 5 分鐘還沒好，信沒有寄出。請稍後再試一次。',
    'mail_already_sent': '這封信已經在 {at} 寄出了。',
    'mail_none': '這份會議紀錄沒有準備好的信件。',
    'mail_preview_failed': '信件預覽失敗，信沒有寄出。',
    'mail_changed': '信件在預覽之後改過了，請重新按寄出。',
    'mail_not_sent': '信沒有寄出。',
    'log_sent': '已寄給 {names}，附件是 {format}',

    # minutes_app.py: words for dates, lengths and formats
    'weekdays': '一,二,三,四,五,六,日',
    'months': '01,02,03,04,05,06,07,08,09,10,11,12',
    'day_label': '{month}/{day:02d}（{weekday}）',
    'day_label_year': '{year}/{month}/{day:02d}（{weekday}）',
    'short_time': '{month}/{day:02d} {time}',
    'len_min': '{m} 分鐘',
    'len_hour': '{h} 小時',
    'fmt_word': 'Word 檔',
    'fmt_pdf': 'PDF 檔',
    'fmt_gdoc': 'Google 文件連結',
    # minutes_app.py: messages
    'job_missing': '找不到這場錄音。',
    'no_file': '這台電腦上找不到這場會議的紀錄檔，現在沒辦法修改。',
    'update_not_git': 'Vinutes 當初不是用 git clone 裝的，沒辦法自動更新。請照 README 的安裝方法重新安裝一次。',
    'update_no_network': '沒辦法下載新版，請確認網路連線正常後，再按一次版本更新。',
    'update_failed': ('沒辦法下載新版。可能是網路不通，或有人改過 Vinutes 資料夾裡的檔案。'
                      '網路正常卻還是失敗，請照 README 的安裝方法重新安裝一次。'),
    'edited_by': '{who} 在 Google 文件上修改',
    'offline_saved': '沒有連上 Google 文件，改過的內容先存在這台電腦，下次存檔或打開這場會議時會再存回。',
    'no_docs_api': ('這台電腦的 Google 連線還沒開啟 Google Docs API，改過的內容先存在這台電腦。'
                    '到「環境設定自檢」的第 8 項按「開啟」就可以補上。'),
    'login_saved': ('Google 登入已經失效，改過的內容先存在這台電腦。'
                    '到「環境設定自檢」的第 7 項重新登入之後，下次存檔會一起存回。'),
    'no_right_saved': ('你的 Google 帳號沒有這份 Google 文件的編輯權限，改過的內容先存在這台電腦。'
                       '文件擁有者開放編輯權限之後，下次存檔會一起存回。'),
    'gone_saved': '找不到這份 Google 文件，可能已經被刪除。改過的內容存在這台電腦的紀錄檔裡。',
    'offline_open': '沒有連上 Google 文件，畫面上是這台電腦上的版本。',
    'login_open': 'Google 登入已經失效，畫面上是這台電腦上的版本。到「環境設定自檢」的第 7 項就可以重新登入。',
    'no_right_open': '你的 Google 帳號沒有這份 Google 文件的權限，畫面上是這台電腦上的版本。',
    'gone_open': '找不到這份 Google 文件，可能已經被刪除，畫面上是這台電腦上的版本。',
    'offline_conflict': '你離線時改的幾段，同事也在 Google 文件上改過，這幾段保留同事的版本：',
    'offline_spare': '。你離線時的版本另外存在「{name}」。',
    'not_applied': '你還沒存回的這幾段沒辦法套到 Google 文件上的版本，請再改一次：',
    'tables_changed': '有人在 Google 文件改了表格的列數，紀錄已換成 Google 文件上的版本。',
    'table_shape': '表格的列或欄沒辦法在這裡增減，這次的修改沒有存。要增減表格的列或欄，請到 Google 文件修改。',
    'ai_tables_offline': '{ai} 這次的修改會增減表格的列或欄，要連上 Google 文件才能存。紀錄沒有變動。',
    'ai_tables_comments': ('{ai} 這次的修改會增減表格的列或欄，要把整份文件重新上傳。Google 文件上還有沒處理的留言，'
                           '重新上傳之後留言會對不到原文，所以紀錄沒有變動。處理完留言再試一次。'),
    'ai_tables_colleague': '同事在 {ai} 修改的同時改了 Google 文件，所以 {ai} 這次的修改沒有存。再試一次，{ai} 會從最新的版本開始改。',
    'whole_comments': 'Google 文件上剛有人留言，這次增減表格的修改沒有存回，紀錄已換成 Google 文件上的版本。',
    'whole_colleague': '同事剛好也在 Google 文件上修改，這次增減表格的修改沒有存回，紀錄已換成 Google 文件上的版本。',
    'rejected_saved': ('Google 文件沒有接受這次的修改，改過的內容先存在這台電腦。'
                       '重新打開這場會議再試一次；還是不行的話，請直接到 Google 文件修改。'),
    'rejected_open': 'Google 文件沒有接受這台電腦上還沒存回的修改，畫面上是這台電腦上的版本。',
    'gs_login': 'Google 登入已經失效，{what}。到「環境設定自檢」的第 7 項重新登入。',
    'gs_offline': '沒有連上 Google，{what}，請再試一次。',
    'gs_other': '{what}，請再試一次。',
    'reply_not_sent': '回覆沒有送出',
    'resolve_not_done': '留言沒有標成已解決',
    'delete_not_done': '這場會議沒有刪除',
    'not_as_planned': '存回 Google 文件之後，有幾段跟預期的不一樣，預覽已經換成 Google 文件上的版本。',
    'unsaved_spare': '你還沒存回的修改另外存在「{name}」，請對照之後再改一次。',
    'change_spare': '這次的修改另外存在「{name}」。',
    'busy_meeting': '這場會議還有別的動作在處理，請稍後再試一次。',
    'not_ready': '這場會議還沒整理好，現在不能修改。',
    'bad_tags': '標籤沒有存好，請再試一次。',
    'bad_project': '專案名稱不能空白。',
    'bad_brief': '小抄沒有存到，再試一次。',
    'item_missing': '找不到這一筆。',
    'check_missing': '找不到這一項。',
    'reply_empty': '回覆是空的。',
    'undo_nothing': '沒有可以復原的修改。',
    'undo_tables': '{ai} 改過表格的列數，沒辦法只復原它改的部分；要改回來請直接到 Google 文件修改。',
    'ai_timeout': '{ai} 改了 10 分鐘還沒改完，已經停止，紀錄沒有變動。',
    'ai_error': '{ai} 修改時出錯，紀錄沒有變動。',
    'ai_nothing': '紀錄沒有需要修改的地方',
    'ai_broken': '{ai} 改出來的紀錄格式不完整，沒有存。',
    'ai_leaks': '{ai} 改出來的紀錄裡有看起來像登入資料的文字，為了安全沒有存。',
    'ai_done': '已照你的話修改',
    'ai_saved_doc': '，已存回 Google 文件',
    'missing_file': '這台電腦上找不到這場會議的紀錄檔「{name}」，可能已經被移走或改了檔名。',
    'missing_showing_doc': '畫面上是 Google 文件的內容，',
    'missing_put_back': '要在這裡修改，請把紀錄檔放回「{folder}」。',
    'reply_attached': '已加進第八章「補充資訊」：{names}',
    # minutes_app.py: the quick buttons, as the activity log names them
    'quick_short': '精簡摘要',
    'quick_detail': '完整詳盡',
    'quick_formal': '正式嚴謹',
    'quick_visual': '視覺呈現',
    'quick_external': '對外版本',
    # minutes_app.py: the activity log
    'where_doc': '在 Google 文件',
    'where_preview': '在預覽',
    'chg_add': '{where}加了一段：「{text}」',
    'chg_remove': '{where}刪掉一段：「{text}」',
    'chg_fill': '{where}補上「{text}」',
    'chg_delete': '{where}刪掉「{text}」',
    'chg_change': '{where}把「{before}」改成「{after}」',
    'log_more_doc_edits': '在 Google 文件還改了 {n} 處',
    'log_table_rows': '在 Google 文件改了表格的列數',
    'log_changed_after_send': '在寄出之後改了內容，寄出去的 {format}還是修改前的版本',
    'log_comment': '在 Google 文件留言：「{text}」',
    'log_resolved': '把 {who} 的留言標為已解決',
    'log_resolved_own': '把 自己 的留言標為已解決',
    'log_resolved_anon': '把一則留言標為已解決',
    'log_replied': '回覆 {who} 的留言：「{text}」',
    'log_replied_own': '回覆 自己 的留言：「{text}」',
    'log_replied_anon': '回覆留言：「{text}」',
    'bounce_no_address': '，信箱地址不存在',
    'log_bounce': '收到退信：寄給 {names} 的信沒有送到{why}',
    'log_learned_term': '記進詞彙表：{text}',
    'log_learned_brief': '記進「{project}」小抄：{text}',
    'log_brief_person': '{name} 加進「{project}」小抄',
    'new_person_label': '新的人名：{name}',
    'log_learned_pref': '記進個人偏好：{text}',
    'log_unlearn': '不要記：{text}',
    'log_relearn': '改回要記：{text}',
    'log_tables_not_saved': '這次增減表格的修改沒有存回 Google 文件',
    'log_attached': '在第八章「補充資訊」加了 {names}',
    'log_noted': '在第八章「補充資訊」補了一段：「{text}」',
    'log_replaced': '把「{old}」改成「{new}」',
    'note_empty': '沒有要加的內容。',
    'replace_missing': '紀錄裡沒有這段文字。要照 get_minutes 拿到的原文完全一樣地複製，粗體、連結的符號也要一起帶；也可能已經有人改過。',
    'replace_lines': '一次只能修改一行：原本的文字和新的文字都不能有換行。',
    'replace_many': '這段文字在紀錄裡出現 {n} 次，要多帶一些前後的字，只對到一個地方才能修改。',
    'log_quick': '照「{label}」改寫內容',
    'log_asked': '照指示修改：「{text}」',
    'log_undo': '復原 {ai} 上一次的修改',
    'log_confirmed': '確認無誤：{label}',
    'log_skipped': '略過：{label}',
    'log_corrected': '修改：{label}，改成「{right}」',
    'correct_empty': '需先填入正確的內容，才能修改',
    'speaker_line_at': '{at} 的句子',
    'speaker_a_line': '一句',
    'log_speaker': '把{what}標成 {who}',
    'log_voice_off': '移除{who}',
    'log_voice_back': '復原{who}',
    # minutes_app.py: what was learned from the user's edits
    'lesson_fill': '補上「{text}」',
    'lesson_delete': '刪掉「{text}」',
    'lesson_term': '以後「{before}」寫成「{after}」',
    'lesson_pref': '以後不寫「{before}」',
    'lesson_style': '照你的寫法：「{text}」',
    'lesson_change': '「{before}」改成「{after}」',

    # speakers.py
    'speakers_no_input': '沒有逐字稿或錄音，沒辦法分辨講者。',
    'speakers_none': '這場會議還沒有分辨講者，沒辦法取名字。',
    'speaker_missing': '找不到這位講者。',
    'line_missing': '找不到這一句。',

    # setup_check.py
    'client_not_google': '這個檔案不是 Google 的用戶端檔案，請選從 Google Cloud 下載的 JSON 檔。',
    'client_web': '這是「網頁應用程式」的用戶端。請改建一個「電腦版應用程式」的用戶端，再下載一次。',
}

STRINGS = {'en': EN, 'zh-TW': ZH}

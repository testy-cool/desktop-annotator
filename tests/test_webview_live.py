"""Real WebKit/X11 regressions; each run uses its own virtual desktop and notes."""
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r'''
import gi, json, time, tempfile, subprocess, os
from pathlib import Path
from datetime import datetime
from desktop_annotator.annotation import Annotation, append_annotation, parse_annotation_list
from desktop_annotator.webview import AnnotatorWindow
from desktop_annotator.capture import TextCandidate

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, Gdk, GLib, WebKit2

def until(predicate):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        if predicate(): return
        time.sleep(.01)
    raise AssertionError("Timed out waiting for WebKit")

def js(script):
    result = []
    errors = []
    def done(view, task, _data):
        try: result.append(json.loads(view.evaluate_javascript_finish(task).to_string()))
        except Exception as error: errors.append(error)
    w.view.evaluate_javascript("JSON.stringify((() => {" + script + "})())", -1, None, None, None, done, None)
    until(lambda: result or errors)
    if errors: raise errors[0]
    return result[0]

with tempfile.TemporaryDirectory() as tmp:
    directory = Path(tmp)
    append_annotation(Annotation("older quote", "older comment", "Older", datetime(2026,10,28,12,0)), directory)
    append_annotation(Annotation("newer quote", "newer comment", "Newer", datetime(2026,10,28,12,1)), directory)
    w = AnnotatorWindow(candidates=[TextCandidate("Selected text", "captured quote")], source="Test window", directory=directory, gtk=Gtk, gdk=Gdk, webkit=WebKit2, glib=GLib)
    loaded = []
    w.view.connect("load-changed", lambda v,e: loaded.append(True) if e == WebKit2.LoadEvent.FINISHED else None)
    w.present()
    until(lambda: loaded)
    assert js("showPane('list'); return document.querySelectorAll('.entry').length") == 2
    assert not js("return $('save').classList.contains('primary')")
    assert js("return document.querySelector('label[for=quote]').textContent") == 'Quote'
    assert js("return document.querySelector('label[for=comment]').textContent") == 'Your note'
    assert not js("return !!$('chips').getClientRects().length")
    # A cleared quote must retain a caret target after filtering and be repairable.
    js("showPane('list'); const q=document.querySelector('.q'); doc.focus(); const range=document.createRange(); range.selectNodeContents(q); const selection=getSelection(); selection.removeAllRanges(); selection.addRange(range); document.execCommand('delete'); $('filter').value='newer'; $('filter').dispatchEvent(new Event('input')); $('filter').value=''; $('filter').dispatchEvent(new Event('input')); return true")
    assert js("return document.querySelector('.q').getBoundingClientRect().height") > 0
    js("const q=document.querySelector('.q'); doc.focus(); const range=document.createRange(); range.selectNodeContents(q); const selection=getSelection(); selection.removeAllRanges(); selection.addRange(range); document.execCommand('insertText',false,'newer quote'); return true")
    assert js("return document.querySelector('.q').innerText") == 'newer quote'
    # Actual Enter must produce a multiline comment that remains saveable.
    js("const c=document.querySelector('.c'); doc.focus(); const range=document.createRange(); range.selectNodeContents(c); range.collapse(false); const selection=getSelection();selection.removeAllRanges();selection.addRange(range); return true")
    window=subprocess.run(['xdotool','search','--onlyvisible','--pid',str(os.getpid()),'--name','Annotate'],capture_output=True,text=True,check=True).stdout.splitlines()[0]
    subprocess.run(['xdotool','windowactivate','--sync',window],check=True)
    subprocess.run(['xdotool','key','Return'],check=True)
    subprocess.run(['xdotool','type','--clearmodifiers','second line'],check=True)
    until(lambda: js("return doc.textContent.includes('second line')"))
    js("$('save').click(); return true")
    until(lambda: 'second line' in (directory/'annotations.md').read_text())
    assert parse_annotation_list((directory/'annotations.md').read_text())[-1].comment == 'newer comment\nsecond line'
    until(lambda: js("return $('liststatus').textContent.includes('Saved')"))
    js("document.querySelector('.q').textContent='draft quote'; doc.dispatchEvent(new Event('input',{bubbles:true})); $('filter').value='older'; $('filter').dispatchEvent(new Event('input')); return true")
    assert js("return document.querySelectorAll('.entry').length") == 1
    assert js("return $('save').classList.contains('primary')")
    assert js("return $('shown').textContent.includes('edited')")
    # Guard all closure paths while this hidden draft exists.
    w.request_close('window')
    until(lambda: js("return !$('close-warning').hidden"))
    assert w.window.get_visible()
    js("$('keep-editing').click(); return true")
    assert js("return $('close-warning').hidden")
    # Adding a different note cannot silently close and lose list edits.
    before_add=(directory/'annotations.md').read_bytes()
    js("showPane('add'); $('comment').value='pending new note'; $('comment').dispatchEvent(new Event('input')); $('add').click(); return true")
    assert (directory/'annotations.md').read_bytes() == before_add
    assert js("return $('pane-list').classList.contains('on')")
    assert js("return $('comment').value") == 'pending new note'
    js("$('copyall').click(); return true")
    clipboard=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    until(lambda: 'draft quote' in (clipboard.wait_for_text() or ''))
    assert 'older quote' in clipboard.wait_for_text()
    js("$('filter').value=''; $('filter').dispatchEvent(new Event('input')); return true")
    assert js("return document.querySelector('.q').innerText") == 'draft quote'
    # Searches use the edited draft, and hidden entries remain in a save.
    js("$('filter').value='draft'; $('filter').dispatchEvent(new Event('input')); $('save').click(); return true")
    until(lambda: 'draft quote' in (directory/'annotations.md').read_text())
    assert len(parse_annotation_list((directory/'annotations.md').read_text())) == 2
    until(lambda: js("return $('liststatus').textContent.includes('Saved')"))
    # Repeated save establishes a new baseline.
    js("document.querySelector('.c').textContent='→ second edit'; doc.dispatchEvent(new Event('input',{bubbles:true})); $('save').click(); return true")
    until(lambda: 'second edit' in (directory/'annotations.md').read_text())
    until(lambda: js("return $('liststatus').textContent.includes('Saved')"))
    # Native Undo must restore a deleted stable entry and clear dirty state.
    js("const range=document.createRange(); range.selectNode(document.querySelector('.entry')); doc.focus(); const selection=getSelection(); selection.removeAllRanges(); selection.addRange(range); document.execCommand('delete'); return true")
    assert js("return $('shown').textContent.includes('deleted')")
    js("document.execCommand('undo'); return true")
    assert js("return entries.length") == 2
    assert js("return document.querySelector('.q').innerText") == 'draft quote'
    assert not js("return $('save').classList.contains('primary')")
    # Deleting a filtered row cannot resurrect it when filter changes.
    js("const range=document.createRange(); range.selectNode(document.querySelector('.entry')); doc.focus(); const selection=getSelection(); selection.removeAllRanges(); selection.addRange(range); document.execCommand('delete'); doc.dispatchEvent(new Event('input',{bubbles:true})); $('filter').value=''; $('filter').dispatchEvent(new Event('input')); return true")
    assert js("return document.querySelectorAll('.entry').length") == 1
    js("$('save').click(); return true")
    until(lambda: len(parse_annotation_list((directory/'annotations.md').read_text())) == 1)
    until(lambda: js("return $('liststatus').textContent.includes('Saved')"))
    # Malformed editable DOM must remain on screen and must not be saved.
    original = (directory/'annotations.md').read_bytes()
    js("document.querySelector('.c').remove(); doc.dispatchEvent(new Event('input',{bubbles:true})); $('filter').value='absent'; $('filter').dispatchEvent(new Event('input')); $('save').click(); return true")
    assert js("return document.querySelectorAll('.entry').length") == 1
    assert (directory/'annotations.md').read_bytes() == original
    js("$('filter').value=''; $('revert').click(); return true")
    until(lambda: js("return !!document.querySelector('.c')"))
    # Unexpected text inside an entry cannot silently disappear on serialization.
    js("document.querySelector('.entry').appendChild(document.createTextNode('orphaned draft text')); doc.dispatchEvent(new Event('input',{bubbles:true})); $('filter').value='missing'; $('filter').dispatchEvent(new Event('input')); $('save').click(); return true")
    assert js("return doc.textContent.includes('orphaned draft text')")
    assert (directory/'annotations.md').read_bytes() == original
    js("$('filter').value=''; $('revert').click(); return true")
    until(lambda: js("return !doc.textContent.includes('orphaned draft text')"))
    # External edits reject the save while preserving the unsaved draft.
    js("document.querySelector('.q').textContent='kept draft'; doc.dispatchEvent(new Event('input',{bubbles:true})); return true")
    append_annotation(Annotation("external addition", "external comment", "External", datetime(2026,10,28,12,2)), directory)
    external = (directory/'annotations.md').read_bytes()
    js("$('save').click(); return true")
    until(lambda: js("return /changed/i.test($('liststatus').textContent)"))
    assert (directory/'annotations.md').read_bytes() == external
    assert js("return document.querySelector('.q').innerText") == 'kept draft'
    # Opening the external editor must retain this conflicting browser draft.
    import desktop_annotator.webview as bridge
    opened=[]
    launch=bridge._launch_sublime
    bridge._launch_sublime=lambda path: opened.append(path)
    try:
        js("$('sublime').click(); return true")
        until(lambda: opened)
        assert w.window.get_visible()
        assert (directory/'annotations.md').read_bytes() == external
        assert js("return document.querySelector('.q').innerText") == 'kept draft'
    finally:
        bridge._launch_sublime=launch
    js("$('revert').click(); return true")
    until(lambda: js("return document.querySelectorAll('.entry').length") == 2)
    # Native rendered checks on both panes at both supported sizes.
    for width,height in [(760,640),(640,560)]:
        w.window.resize(width,height)
        until(lambda: js("return innerWidth") == width)
        widths=[]
        for pane in ['add','list']:
            data=js("showPane("+json.dumps(pane)+"); return {width:document.querySelector('.pane.on').getBoundingClientRect().width, small:[...document.querySelectorAll('*')].filter(e=>e.getClientRects().length && e.textContent.trim() && !['SCRIPT','STYLE'].includes(e.tagName) && parseFloat(getComputedStyle(e).fontSize)<12).map(e=>e.className), overflow:document.documentElement.scrollWidth>innerWidth}")
            assert not data['small'], data
            assert not data['overflow'], data
            widths.append(data['width'])
        assert widths[0] == widths[1], widths
    # Unrecognized file content is visible as an error and saving is blocked.
    (directory/'annotations.md').write_bytes(b'# Unrecognized preamble\n'+external)
    js("$('revert').click(); return true")
    until(lambda: js("return $('save').disabled"))
    before=(directory/'annotations.md').read_bytes()
    js("$('save').click(); return true")
    assert (directory/'annotations.md').read_bytes()==before
    # Appending still preserves unrecognized bytes and closes the actual window.
    js("showPane('add'); $('comment').value='added comment'; $('add').click(); return true")
    until(lambda: b'added comment' in (directory/'annotations.md').read_bytes())
    assert (directory/'annotations.md').read_bytes().startswith(before)
# A malformed daily file must produce a usable diagnostic window, not a crash.
with tempfile.TemporaryDirectory() as tmp:
    directory=Path(tmp)
    daily=directory/'2026-08-19.md'
    daily.write_bytes(b'\xff')
    w=AnnotatorWindow(candidates=[], source='Test', directory=directory, gtk=Gtk, gdk=Gdk, webkit=WebKit2, glib=GLib)
    loaded=[]
    w.view.connect('load-changed',lambda v,e: loaded.append(True) if e==WebKit2.LoadEvent.FINISHED else None)
    w.present()
    until(lambda: loaded)
    assert js("return $('save').disabled")
    assert js("return $('saveproblem').textContent.includes('Could not load annotations')")
    assert daily.read_bytes()==b'\xff'
    assert not (directory/'annotations.md').exists()
    w.window.destroy()

# Dirty native close requests warn; editing disarms repeated-discard shortcuts.
with tempfile.TemporaryDirectory() as tmp:
    directory=Path(tmp)
    w=AnnotatorWindow(candidates=[TextCandidate('Selected text','Captured')],source='Test',directory=directory,gtk=Gtk,gdk=Gdk,webkit=WebKit2,glib=GLib)
    loaded=[];closed=[]
    w.view.connect('load-changed',lambda v,e: loaded.append(True) if e==WebKit2.LoadEvent.FINISHED else None)
    w.window.connect('destroy',lambda *_: closed.append(True))
    w.present();until(lambda: loaded)
    js("$('comment').value='Unsaved note'; $('comment').dispatchEvent(new Event('input')); return true")
    w.window.close()
    until(lambda: js("return !$('close-warning').hidden"))
    assert not closed
    assert js("return $('comment').value") == 'Unsaved note'
    # Repeated pointer close/cancel still requires the explicit discard control.
    js("$('close').click(); $('close').click(); $('cancel').click(); return true")
    assert not closed
    js("$('keep-editing').click(); dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'})); return true")
    until(lambda: js("return !$('close-warning').hidden"))
    assert not closed
    js("$('comment').value+=' edit'; $('comment').dispatchEvent(new Event('input')); dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'})); return true")
    assert not closed
    assert js("return !$('close-warning').hidden")
    js("$('keep-editing').click(); return true")
    w.request_close('shortcut')
    until(lambda: js("return !$('close-warning').hidden"))
    assert not closed
    w.request_close('shortcut')
    until(lambda: closed)
    assert not (directory/'annotations.md').exists()

print('WebKit draft, save, conflict, malformed file and rendered checks passed')
# Exercise the real executable, keyboard path and second-launch signal.
processes = []
try:
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, ANNOTATIONS_DIR=tmp)
        env.pop('DESKTOP_ANNOTATOR_UI', None)
        selection = subprocess.Popen(['xclip','-selection','primary','-in','-quiet'],env=env,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True)
        processes.append(selection)
        selection.stdin.write('live selected quote')
        selection.stdin.close()
        def xdo(*args):
            return subprocess.run(['xdotool',*args],env=env,capture_output=True,text=True,timeout=4).stdout.strip()
        def launch():
            app = subprocess.Popen(['/usr/bin/python3','annotate.py'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            processes.append(app)
            found = []
            def visible():
                assert app.poll() is None, 'Application exited before showing window'
                window=xdo('search','--onlyvisible','--pid',str(app.pid),'--name','Annotate')
                if window: found.append(window.splitlines()[0])
                return found
            until(visible)
            return app,found[0]
        app,window=launch()
        xdo('windowactivate','--sync',window)
        assert xdo('getwindowfocus') == window
        # Wait for the local HTML page to load and place focus in the comment.
        time.sleep(.5)
        xdo('type','--clearmodifiers','--delay','1','live keyboard comment')
        xdo('key','--clearmodifiers','ctrl+Return')
        assert app.wait(timeout=8) == 0
        saved=parse_annotation_list((Path(tmp)/'annotations.md').read_text())
        assert len(saved)==1 and saved[0].quote=='live selected quote' and saved[0].comment=='live keyboard comment', saved
        app,window=launch()
        second=subprocess.run(['/usr/bin/python3','annotate.py'],env=env,capture_output=True,text=True,timeout=8)
        assert second.returncode == 0 and app.wait(timeout=8) == 0
        app,window=launch()
        xdo('windowactivate','--sync',window)
        time.sleep(.5)
        xdo('type','--clearmodifiers','unsaved keyboard note')
        second=subprocess.run(['/usr/bin/python3','annotate.py'],env=env,capture_output=True,text=True,timeout=8)
        assert second.returncode == 0
        time.sleep(.2)
        assert app.poll() is None, 'First toggle discarded a dirty note'
        # Typing after the warning disarms its repeat-to-discard shortcut.
        xdo('key','Escape')
        time.sleep(.1)
        assert app.poll() is None
        xdo('key','Escape')
        assert app.wait(timeout=8) == 0
        assert len(parse_annotation_list((Path(tmp)/'annotations.md').read_text())) == 1
finally:
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
print('Real capture, keyboard save and second-launch toggle passed')

'''


class LiveWebKitTests(unittest.TestCase):
    @unittest.skipUnless(all(shutil.which(tool) for tool in ('Xvfb','metacity','xclip','xdotool')), 'Xvfb and metacity required')
    def test_real_webkit_workflow(self):
        server = subprocess.Popen(['Xvfb', '-displayfd', '1', '-screen', '0', '1400x900x24', '-nolisten', 'tcp'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        wm = None
        try:
            self.assertTrue(select.select([server.stdout], [], [], 5)[0], 'Xvfb startup timed out')
            with tempfile.TemporaryDirectory() as runtime:
                env = dict(os.environ, DISPLAY=':'+server.stdout.readline().strip(), GDK_BACKEND='x11', XDG_RUNTIME_DIR=runtime)
                wm = subprocess.Popen(['metacity', '--sm-disable'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                result = subprocess.run(['/usr/bin/python3', '-c', SCRIPT], cwd=ROOT, env=env, text=True, capture_output=True, timeout=65)
                self.assertEqual(result.returncode, 0, result.stdout+'\n'+result.stderr)
        finally:
            if wm is not None:
                wm.terminate()
                wm.wait(timeout=5)
            server.terminate()
            server.wait(timeout=5)
            server.stdout.close()

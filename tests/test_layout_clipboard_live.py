"""Native selection clipboard and persisted split-layout regressions."""
import unittest
from unittest.mock import patch

import tests.test_webview_live as webkit_fixture

BOOTSTRAP_END = '    assert js("showPane'
assert BOOTSTRAP_END in webkit_fixture.SCRIPT, 'Live WebKit bootstrap marker changed'
PREFIX = webkit_fixture.SCRIPT.split(BOOTSTRAP_END, 1)[0]


def run_webkit(body):
    with patch.object(webkit_fixture, 'SCRIPT', PREFIX + body):
        webkit_fixture.LiveWebKitTests('test_real_webkit_workflow').test_real_webkit_workflow()


class ClipboardSelectionTests(unittest.TestCase):
    def test_native_copy_and_paste_preserve_note_boundaries(self):
        run_webkit(r'''
    js("showPane('list'); return true")
    assert js("return doc.querySelectorAll('.sep').length") == 0
    assert not js("return doc.textContent.includes('---')")
    window=subprocess.run(['xdotool','search','--onlyvisible','--pid',str(os.getpid()),'--name','Annotate'],capture_output=True,text=True,check=True).stdout.splitlines()[0]
    subprocess.run(['xdotool','windowactivate','--sync',window],check=True)
    clipboard=Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    def native_copy(select):
        js(select+'; return true')
        clipboard.set_text('copy pending',-1)
        subprocess.run(['xdotool','key','--clearmodifiers','ctrl+c'],check=True)
        until(lambda: clipboard.wait_for_text() != 'copy pending')
        return clipboard.wait_for_text()
    all_text='newer quote\n→ newer comment\n---\nolder quote\n→ older comment'
    assert native_copy("$('selectall').click()") == all_text
    assert 'Newer' not in clipboard.wait_for_text()
    assert '2026-' not in clipboard.wait_for_text()
    # A selection within one field is copied exactly, with no separator.
    def select_fields(start_selector,start,end_selector,end):
        return "doc.focus(); const r=document.createRange(); r.setStart(document.querySelector("+json.dumps(start_selector)+").firstChild,"+str(start)+"); r.setEnd(document.querySelector("+json.dumps(end_selector)+").firstChild,"+str(end)+"); const s=getSelection(); s.removeAllRanges();s.addRange(r)"
    assert native_copy(select_fields('.q',2,'.q',8)) == 'newer quote'[2:8]
    assert native_copy(select_fields('.q',6,'.c',7)) == 'quote\n→ newer'
    # Crossing entries adds exactly one delimiter, preserving both partial ends.
    assert native_copy(select_fields('.entry:first-child .c',4,'.entry:last-child .q',5)) == 'wer comment\n---\nolder'
    assert native_copy("doc.focus();getSelection().setBaseAndExtent(document.querySelector('.entry:last-child .q').firstChild,5,document.querySelector('.entry:first-child .c').firstChild,4)") == 'wer comment\n---\nolder'
    js("document.querySelector('.q').textContent='  padded  ';doc.dispatchEvent(new Event('input',{bubbles:true}));return true")
    assert native_copy("doc.focus();const r=document.createRange();r.selectNodeContents(document.querySelector('.q'));const s=getSelection();s.removeAllRanges();s.addRange(r)") == '  padded  '
    js("document.querySelector('.q').innerHTML='line one<br>line two'; doc.dispatchEvent(new Event('input',{bubbles:true})); return true")
    assert native_copy("doc.focus(); const r=document.createRange();r.selectNodeContents(document.querySelector('.q'));const s=getSelection();s.removeAllRanges();s.addRange(r)") == 'line one\nline two'
    # Filtered selection copies only visible notes, whereas Copy all keeps hidden drafts.
    js("$('filter').value='older'; $('filter').dispatchEvent(new Event('input')); return true")
    visible='older quote\n→ older comment'
    assert native_copy("$('selectall').click()") == visible
    js("$('copyall').click(); return true")
    expected='line one\nline two\n→ newer comment\n---\nolder quote\n→ older comment'
    until(lambda: clipboard.wait_for_text()==expected)
    # Exercise the actual native paste path into the Add form.
    js("showPane('add'); $('comment').value=''; $('comment').focus(); return true")
    subprocess.run(['xdotool','key','--clearmodifiers','ctrl+v'],check=True)
    until(lambda: js("return $('comment').value") == expected)
    assert not js("return doc.textContent.includes('---')")
''')


class DragSelectionTests(unittest.TestCase):
    def test_drag_cannot_move_text_out_of_the_saved_list(self):
        run_webkit(r'''
    js("$('layout').value='split';$('layout').dispatchEvent(new Event('change'));showPane('list');return true")
    until(lambda: js('return innerWidth')==1200)
    before=js("return doc.innerText")
    point=js("const a=doc.querySelector('.entry:first-child .q').firstChild,b=doc.querySelector('.entry:last-child .q').firstChild;doc.focus();const selected=document.createRange();selected.setStart(a,2);selected.setEnd(b,5);const s=getSelection();s.removeAllRanges();s.addRange(selected);const char=document.createRange();char.setStart(a,3);char.setEnd(a,4);const r=char.getBoundingClientRect(),t=$('comment').getBoundingClientRect();window.dragStarted=false;window.dropSeen=false;window.dragLog=[];for(const type of ['dragenter','dragover','drop','dragend'])document.addEventListener(type,e=>window.dragLog.push([type,e.target.id||e.target.className,e.clientX,e.clientY,e.dataTransfer.effectAllowed,e.dataTransfer.dropEffect]));doc.addEventListener('dragstart',()=>window.dragStarted=true);$('comment').addEventListener('drop',()=>window.dropSeen=true);return {sx:r.left+r.width/2,sy:r.top+r.height/2,tx:t.left+30,ty:t.top+30}")
    ox,oy=w.window.get_position()
    origin=w.window.get_window().get_origin()
    point['windowPosition']=[ox,oy];point['clientOrigin']=list(origin)
    def mouse(*args):subprocess.run(['xdotool',*map(str,args)],check=True)
    def settle():
        deadline=time.monotonic()+.18
        until(lambda:time.monotonic()>deadline)
    mouse('mousemove','--sync',round(ox+point['sx']),round(oy+point['sy']));settle()
    mouse('mousedown',1);settle()
    mouse('mousemove','--sync',round(ox+point['sx']+15),round(oy+point['sy']));settle()
    mouse('mousemove','--sync',round(ox+point['tx']),round(oy+point['ty']));settle()
    mouse('mousemove','--sync',round(ox+point['tx']+8),round(oy+point['ty']+8));settle()
    mouse('mousemove','--sync',round(ox+point['tx']+12),round(oy+point['ty']+8));settle()
    mouse('mouseup',1);settle()
    assert js('return window.dragStarted'), 'Test did not initiate a native selection drag'
    assert js("return window.dragLog.some(e=>e[0]==='dragover'&&e[1]==='comment')"), point
    assert js('return doc.innerText') == before, (before,js("return {text:doc.innerText,events:window.dragLog,note:$('comment').value}"))
    assert js("return $('comment').value") == ''
    assert js("return $('addstatus').textContent.includes('Ctrl+C')")
    assert not js('return listDirty()')
''')


class SplitLayoutTests(unittest.TestCase):
    def test_layout_persists_and_preserves_drafts_focus_and_selection(self):
        run_webkit(r'''
    # Switching layouts must not replace the editable document or lose Undo state.
    js("showPane('list'); window.originalEntry=doc.querySelector('.entry'); document.querySelector('.q').textContent='split draft'; doc.dispatchEvent(new Event('input',{bubbles:true})); const r=document.createRange();r.selectNodeContents(document.querySelector('.q'));const s=getSelection();s.removeAllRanges();s.addRange(r); $('layout').value='split';$('layout').dispatchEvent(new Event('change')); return true")
    from desktop_annotator.settings import load_layout
    until(lambda: load_layout()=='split')
    until(lambda: js('return innerWidth')>=1000)
    geometry=js("const a=$('pane-add').getBoundingClientRect(),b=$('pane-list').getBoundingClientRect();return {left:a.left,right:b.left,a:a.width,b:b.width,visibleA:!!a.height,visibleB:!!b.height,same:window.originalEntry===doc.querySelector('.entry'),selection:getSelection().toString()}")
    assert geometry['visibleA'] and geometry['visibleB'] and geometry['left'] < geometry['right'], geometry
    assert abs(geometry['a']-geometry['b']) <= 1,geometry
    for width in [1000,1200]:
        w.window.resize(width,640)
        until(lambda: js('return innerWidth')==width)
        metrics=js("return {small:[...document.querySelectorAll('*')].filter(e=>e.getClientRects().length&&e.textContent.trim()&&!['SCRIPT','STYLE'].includes(e.tagName)&&parseFloat(getComputedStyle(e).fontSize)<12).map(e=>e.className),overflow:document.documentElement.scrollWidth>innerWidth,panes:[...document.querySelectorAll('.pane')].map(e=>({width:e.clientWidth,scroll:e.scrollWidth}))}")
        assert not metrics['small'] and not metrics['overflow'],metrics
        assert all(p['scroll']<=p['width'] for p in metrics['panes']),metrics
    assert geometry['same'] and geometry['selection']=='split draft',geometry
    assert js("return document.querySelector('.q').innerText")=='split draft'
    # Ctrl+Enter routes to the focused pane while both are visible.
    js("$('comment').value='pending Add draft';$('comment').dispatchEvent(new Event('input')); doc.focus(); dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',ctrlKey:true})); return true")
    until(lambda: 'split draft' in (directory/'annotations.md').read_text())
    assert js("return $('comment').value")=='pending Add draft'
    assert w.window.get_visible()
    w.request_close('window')
    until(lambda: js("return !$('close-warning').hidden"))
    assert js("return $('close-message').textContent.includes('Add')")
    assert w.window.get_visible()
    js("$('keep-editing').click(); return true")
    # A second host gets the saved split mode, with no dependency on localStorage.
    other=AnnotatorWindow(candidates=[],source='Test',directory=directory,gtk=Gtk,gdk=Gdk,webkit=WebKit2,glib=GLib)
    assert other.layout=='split'
    other.window.destroy()
    # Native sizes and DOM switch back without dropping either pane's draft.
    js("$('layout').value='tabs';$('layout').dispatchEvent(new Event('change')); return true")
    until(lambda: load_layout()=='tabs')
    until(lambda: js('return innerWidth')==760)
    assert js("return $('comment').value")=='pending Add draft'
    assert js("return document.querySelector('.q').innerText")=='split draft'
    # Persistence errors restore the selector/layout without replacing draft DOM.
    result=js("window.rollbackEntry=doc.querySelector('.entry');applyLayout('split');fromHost({kind:'layoutError',layout:'tabs',status:'Could not save layout'});return {tabs:!$('workspace').classList.contains('split'),value:$('layout').value,same:window.rollbackEntry===doc.querySelector('.entry'),note:$('comment').value}")
    assert result == {'tabs':True,'value':'tabs','same':True,'note':'pending Add draft'},result
    # The left input pane also receives Ctrl+Enter while both panes are visible.
    js("$('layout').value='split';$('layout').dispatchEvent(new Event('change'));return true")
    until(lambda: load_layout()=='split')
    js("$('comment').focus();dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',ctrlKey:true}));return true")
    until(lambda: 'pending Add draft' in (directory/'annotations.md').read_text())
''')

import { AfterViewInit, Component, ElementRef, forwardRef, Input, OnDestroy, Pipe, PipeTransform, signal, ViewChild } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';
import type Quill from 'quill';

export function richTextHtml(value: string | null | undefined): string {
  const text = value || '';
  if (/<\/?[a-z][^>]*>/i.test(text)) return text;
  return text.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('\n','<br>');
}

@Pipe({ name:'richText', standalone:true })
export class RichTextPipe implements PipeTransform {
  transform(value:string|null|undefined) { return richTextHtml(value); }
}

let editorSequence = 0;
@Component({
  selector:'m-rich-text', standalone:true,
  providers:[{provide:NG_VALUE_ACCESSOR,useExisting:forwardRef(()=>RichTextEditor),multi:true}],
  template:`<div class="rich-text-field" [class.rte-disabled]="disabled" [class.rte-over-limit]="length() > maxLength">
    <div class="rte-label" [id]="id + '-label'">{{ label }}</div>
    <div class="rte-frame"><div #toolbar class="rte-toolbar" role="toolbar" [attr.aria-label]="label + ' formatting'">
      <span class="ql-formats"><button type="button" class="ql-header" value="2" title="Heading" aria-label="Heading" [disabled]="disabled"></button><button type="button" class="ql-header" value="3" title="Subheading" aria-label="Subheading" [disabled]="disabled"></button></span>
      <span class="ql-formats"><button type="button" class="ql-bold" title="Bold" aria-label="Bold" [disabled]="disabled"></button><button type="button" class="ql-italic" title="Italic" aria-label="Italic" [disabled]="disabled"></button><button type="button" class="ql-underline" title="Underline" aria-label="Underline" [disabled]="disabled"></button><button type="button" class="ql-strike" title="Strikethrough" aria-label="Strikethrough" [disabled]="disabled"></button></span>
      <span class="ql-formats"><button type="button" class="ql-list" value="bullet" title="Bullet list" aria-label="Bullet list" [disabled]="disabled"></button><button type="button" class="ql-list" value="ordered" title="Numbered list" aria-label="Numbered list" [disabled]="disabled"></button><button type="button" class="ql-blockquote" title="Quote" aria-label="Quote" [disabled]="disabled"></button></span>
      <span class="ql-formats"><button type="button" class="ql-link" title="Insert link" aria-label="Insert link" [disabled]="disabled"></button><button type="button" class="ql-clean" title="Clear formatting" aria-label="Clear formatting" [disabled]="disabled"></button></span>
      <span class="ql-formats"><button type="button" title="Undo" aria-label="Undo" [disabled]="disabled" (click)="undo()">↶</button><button type="button" title="Redo" aria-label="Redo" [disabled]="disabled" (click)="redo()">↷</button></span>
    </div><div #editor [style.--editor-height]="minHeight + 'px'"></div></div>
    @if (failed()) { <p class="rte-error" role="alert">The editor could not load. Refresh the page and try again.</p> }
    <div class="rte-count" [id]="id + '-count'" [class.rte-error]="length() > maxLength">{{ length() }} / {{ maxLength }} characters @if (length() > maxLength) { <span>— shorten the text before saving.</span> }</div>
  </div>`,
})
export class RichTextEditor implements ControlValueAccessor, AfterViewInit, OnDestroy {
  @Input() label = 'Description'; @Input() placeholder = 'Write here…'; @Input() maxLength = 20000; @Input() minHeight = 160;
  @ViewChild('editor',{static:true}) container!:ElementRef<HTMLDivElement>;
  @ViewChild('toolbar',{static:true}) toolbar!:ElementRef<HTMLDivElement>;
  id = `rich-text-${++editorSequence}`; length = signal(0); failed = signal(false); private formDisabled = false; private inputReadOnly = false;
  get disabled() { return this.formDisabled || this.inputReadOnly; }
  private quill?:Quill; private value = ''; private destroyed = false; private onChange: (value:string)=>void = ()=>{}; private onTouched:()=>void = ()=>{};
  @Input() set readOnly(value:boolean) { this.inputReadOnly=value; this.quill?.enable(!this.disabled); }
  writeValue(value: string|null|undefined) { const next = value || ''; if (next === this.value) return; this.value = next; this.applyValue(); }
  registerOnChange(fn:(value:string)=>void) { this.onChange=fn; }
  registerOnTouched(fn:()=>void) { this.onTouched=fn; }
  setDisabledState(disabled:boolean) { this.formDisabled=disabled; this.quill?.enable(!this.disabled); }
  async ngAfterViewInit() {
    try {
      const {default:Quill} = await import('quill');
      if (this.destroyed) return;
      this.quill = new Quill(this.container.nativeElement, {
        theme:'snow', placeholder:this.placeholder, readOnly:this.disabled,
        formats:['header','bold','italic','underline','strike','list','blockquote','link'],
        modules:{toolbar:this.toolbar.nativeElement,history:{userOnly:true}},
      });
      this.quill.root.setAttribute('role','textbox');
      this.quill.root.setAttribute('aria-multiline','true');
      this.quill.root.setAttribute('aria-labelledby',this.id+'-label');
      this.quill.root.setAttribute('aria-describedby',this.id+'-count');
      this.applyValue();
      this.quill.on('text-change',this.changed);
      this.quill.on('selection-change',this.selectionChanged);
      this.quill.root.addEventListener('blur',this.touched);
    } catch { if (!this.destroyed) this.failed.set(true); }
  }
  private applyValue() {
    if (!this.quill) return;
    this.quill.setContents(this.quill.clipboard.convert({html:richTextHtml(this.value)}),'silent');
    this.quill.history.clear(); this.length.set(this.quill.getText().replace(/\n$/,'').length);
  }
  private changed = () => {
    if (!this.quill) return;
    const text = this.quill.getText().replace(/\n$/,'');
    this.length.set(text.length);
    this.value = text.trim() ? this.quill.getSemanticHTML() : '';
    this.onChange(this.value);
  };
  private touched=()=>this.onTouched();
  private selectionChanged=()=> { if (!this.quill?.hasFocus()) this.onTouched(); };
  undo() { this.quill?.history.undo(); }
  redo() { this.quill?.history.redo(); }
  ngOnDestroy() { this.destroyed=true; this.quill?.off('text-change',this.changed); this.quill?.off('selection-change',this.selectionChanged); this.quill?.root.removeEventListener('blur',this.touched); this.quill=undefined; }
}

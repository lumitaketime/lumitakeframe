import * as React from 'react';
import { ICONS } from './icons.js';

const { useState, useRef, useEffect, useContext, createContext, useCallback, useId } = React;

/* ---------- helpers ---------- */
const cx = (...a) => a.filter(Boolean).join(' ');
const tintVar = (t) => (/^gray/.test(t) ? 'var(--' + t + ')' : 'var(--system-' + t + ')');
const PlatformContext = createContext('mac');
const usePlatform = (p) => {
  const ctx = useContext(PlatformContext);
  return p || ctx || 'mac';
};
/** Type-style classes from tokens.css, per platform. */
const TYPE = {
  mac: { largeTitle: 'mac-large-title-em', title2: 'mac-title-2', title3: 'mac-title-3', headline: 'mac-headline', body: 'mac-body', bodyEm: 'mac-body-em', callout: 'mac-callout', sub: 'mac-subheadline', footnote: 'mac-footnote', caption: 'mac-caption-1' },
  ios: { largeTitle: 'ios-large-title-em', title2: 'ios-title-2-em', title3: 'ios-title-3', headline: 'ios-headline', body: 'ios-body', bodyEm: 'ios-body-em', callout: 'ios-callout', sub: 'ios-subheadline', footnote: 'ios-footnote', caption: 'ios-caption-2' },
};
const useControlled = (value, defaultValue, onChange) => {
  const [inner, setInner] = useState(defaultValue);
  const isControlled = value !== undefined;
  const current = isControlled ? value : inner;
  const set = useCallback((v, ...rest) => {
    if (!isControlled) setInner(v);
    if (onChange) onChange(v, ...rest);
  }, [isControlled, onChange]);
  return [current, set];
};
const useDismiss = (open, ref, onClose) => {
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) onClose(); };
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey); };
  }, [open, ref, onClose]);
};

/* ---------- Icon ---------- */
const WEIGHT = { regular: 1.7, medium: 1.9, semibold: 2.1, bold: 2.4 };
/** Interface icon from the system's 24×24 set. Decorative unless `title` is given. */
export function Icon({ name, size = 17, weight = 'regular', title, className, style }) {
  const body = ICONS[name];
  if (!body) return null;
  const a11y = title ? { role: 'img', 'aria-label': title } : { 'aria-hidden': true, focusable: 'false' };
  return (
    <svg className={cx('lg-icon', className)} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={WEIGHT[weight] || WEIGHT.regular} strokeLinecap="round" strokeLinejoin="round"
      {...a11y} dangerouslySetInnerHTML={{ __html: (title ? '<title>' + title.replace(/[<&]/g, '') + '</title>' : '') + body }} />
  );
}
export const iconNames = Object.keys(ICONS);

/* ---------- ContentLayer ---------- */
const MOSAIC = ['orange', 'blue', 'green', 'pink', 'yellow', 'indigo', 'teal', 'brown', 'red', 'mint', 'purple', 'cyan', 'blue'];
/** The content layer: the app's own content and background, under the Liquid Glass layer. Sets the platform for everything inside. */
export function ContentLayer({ platform = 'mac', tone = 'plain', padded = true, className, style, children }) {
  return (
    <PlatformContext.Provider value={platform}>
      <div className={cx('lg-content', 'lg-' + platform, 'lg-tone-' + tone, padded && 'lg-padded', className)} style={style}>
        {tone === 'media' && (
          <div className="lg-mosaic" aria-hidden="true">
            {MOSAIC.map((c, i) => <span key={i} style={{ background: 'var(--system-' + c + ')' }} />)}
          </div>
        )}
        <div className="lg-content-inner">{children}</div>
      </div>
    </PlatformContext.Provider>
  );
}

/* ---------- Glass ---------- */
/** Liquid Glass material for the functional layer (controls and navigation) — never for content. */
export function Glass({ variant = 'regular', shape = 'rounded', dim = false, interactive = false, as: Tag = 'div', className, style, children, ...rest }) {
  return (
    <Tag className={cx('lg-glass', 'lg-glass-' + variant, 'lg-shape-' + shape, dim && 'lg-glass-dimmed', interactive && 'lg-glass-interactive', className)} style={style} {...rest}>
      {children}
    </Tag>
  );
}

/* ---------- Progress ---------- */
/** Determinate bar or ring, or an indeterminate spinner / bar. */
export function ProgressIndicator({ kind = 'bar', value, label, size = 'regular', className }) {
  const platform = usePlatform();
  const determinate = typeof value === 'number';
  const pct = determinate ? Math.max(0, Math.min(1, value)) : 0;
  const aria = { role: 'progressbar', 'aria-label': label || '進度', ...(determinate ? { 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': Math.round(pct * 100) } : {}) };
  if (kind === 'spinner' || (kind === 'circular' && !determinate)) {
    const px = size === 'small' ? 16 : size === 'large' ? 32 : 20;
    return (
      <span className={cx('lg-spinner', className)} style={{ width: px, height: px }} {...aria}>
        {Array.from({ length: 8 }, (_, i) => <i key={i} style={{ transform: 'rotate(' + i * 45 + 'deg)', animationDelay: (i - 8) * 0.125 + 's' }} />)}
      </span>
    );
  }
  if (kind === 'circular') {
    const px = size === 'small' ? 16 : size === 'large' ? 32 : 22;
    const r = 9, len = 2 * Math.PI * r;
    return (
      <svg className={cx('lg-ring', className)} width={px} height={px} viewBox="0 0 24 24" {...aria}>
        <circle cx="12" cy="12" r={r} className="lg-ring-track" />
        <circle cx="12" cy="12" r={r} className="lg-ring-fill" strokeDasharray={len} strokeDashoffset={len * (1 - pct)} transform="rotate(-90 12 12)" />
      </svg>
    );
  }
  return (
    <div className={cx('lg-bar', !determinate && 'lg-bar-indeterminate', 'lg-bar-' + platform, className)} {...aria}>
      <span style={determinate ? { width: pct * 100 + '%' } : undefined} />
    </div>
  );
}

/* ---------- Button ---------- */
/** Initiates an instantaneous action. Style (variant), role and size per the HIG. */
export const Button = React.forwardRef(function Button({
  variant = 'bordered', role = 'normal', size = 'regular', shape = 'capsule', icon, iconOnly = false,
  loading = false, loadingLabel, disabled, platform: p, className, children, type = 'button', ...rest
}, ref) {
  const platform = usePlatform(p);
  const label = loading && loadingLabel ? loadingLabel : children;
  return (
    <button ref={ref} type={type} disabled={disabled || loading} aria-busy={loading || undefined}
      className={cx('lg-btn', 'lg-btn-' + variant, 'lg-btn-' + size, 'lg-btn-' + platform, 'lg-btn-shape-' + (iconOnly && shape === 'capsule' ? 'circle' : shape),
        role !== 'normal' && 'lg-btn-role-' + role, iconOnly && 'lg-btn-icononly', className)}
      {...rest}>
      {loading ? <ProgressIndicator kind="spinner" size="small" label={typeof label === 'string' ? label : '處理中'} />
        : icon ? <Icon name={icon} size={size === 'mini' || size === 'small' ? 13 : platform === 'ios' ? 19 : 15} weight={platform === 'ios' ? 'medium' : 'regular'} /> : null}
      {iconOnly ? null : label != null ? <span className="lg-btn-label">{label}</span> : null}
    </button>
  );
});

/* ---------- Menu ---------- */
/** A menu panel: commands, options or states, grouped by separators. */
export function Menu({ items = [], onSelect, onClose, width, autoFocus = false, platform: p, className, style }) {
  const platform = usePlatform(p);
  const ref = useRef(null);
  const showChecks = items.some((it) => it && it.checked !== undefined);
  useEffect(() => {
    if (autoFocus && ref.current) {
      const first = ref.current.querySelector('[role^="menuitem"]:not([aria-disabled="true"])');
      if (first) first.focus();
    }
  }, [autoFocus]);
  const onKeyDown = (e) => {
    const els = Array.from(ref.current.querySelectorAll('[role^="menuitem"]:not([aria-disabled="true"])'));
    const i = els.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); (els[i + 1] || els[0]).focus(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); (els[i - 1] || els[els.length - 1]).focus(); }
    if (e.key === 'Escape' && onClose) onClose();
  };
  return (
    <div ref={ref} role="menu" className={cx('lg-menu', 'lg-glass', 'lg-glass-regular', 'lg-menu-' + platform, className)} style={{ width, ...style }} onKeyDown={onKeyDown}>
      {items.map((it, i) => {
        if (!it) return null;
        if (it.separator) return <div key={i} role="separator" className="lg-menu-sep" />;
        if (it.header) return <div key={i} className={cx('lg-menu-header', TYPE[platform].sub)}>{it.header}</div>;
        const roleName = it.checked !== undefined ? 'menuitemcheckbox' : 'menuitem';
        const act = () => {
          if (it.disabled) return;
          if (it.onSelect) it.onSelect(it);
          if (onSelect) onSelect(it);
        };
        return (
          <div key={i} role={roleName} tabIndex={it.disabled ? -1 : 0} aria-disabled={it.disabled || undefined}
            aria-checked={it.checked !== undefined ? !!it.checked : undefined} aria-haspopup={it.submenu ? 'menu' : undefined}
            className={cx('lg-menu-item', TYPE[platform].body, it.destructive && 'lg-menu-destructive', it.disabled && 'lg-menu-disabled')}
            onClick={act} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); act(); } }}>
            {showChecks && <span className="lg-menu-check">{it.checked ? <Icon name="checkmark" size={platform === 'ios' ? 17 : 13} weight="semibold" /> : null}</span>}
            {it.icon && <Icon name={it.icon} size={platform === 'ios' ? 19 : 15} className="lg-menu-icon" />}
            <span className="lg-menu-label">{it.label}</span>
            {it.shortcut && <span className="lg-menu-shortcut">{it.shortcut}</span>}
            {it.submenu && <Icon name="chevron-right" size={12} weight="semibold" className="lg-menu-chev" />}
          </div>
        );
      })}
    </div>
  );
}

/* ---------- PullDownButton ---------- */
/** A button that reveals a menu of actions (not a choice of value — use PopUpButton for that). */
export function PullDownButton({ label, icon, items = [], variant = 'bordered', size = 'regular', iconOnly = false, disabled, menuWidth = 220, align = 'start', className }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, wrap, close);
  return (
    <span ref={wrap} className={cx('lg-dropdown', className)}>
      <Button variant={variant} size={size} icon={icon} iconOnly={iconOnly} disabled={disabled} aria-haspopup="menu" aria-expanded={open} aria-label={iconOnly ? label : undefined}
        onClick={() => setOpen((o) => !o)}>
        {label}{!iconOnly && <Icon name="chevron-down" size={11} weight="semibold" className="lg-btn-trailing" />}
      </Button>
      {open && <Menu items={items} width={menuWidth} autoFocus onClose={close} onSelect={close} className={cx('lg-dropdown-menu', align === 'end' && 'lg-align-end')} />}
    </span>
  );
}

/* ---------- PopUpButton ---------- */
/** Shows the current choice of a flat list of mutually exclusive options; opens a menu to change it. */
export function PopUpButton({ options = [], value, defaultValue, onChange, label, disabled, width, menuWidth, className }) {
  const platform = usePlatform();
  const [current, setCurrent] = useControlled(value, defaultValue !== undefined ? defaultValue : options[0] && options[0].value, onChange);
  const [open, setOpen] = useState(false);
  const wrap = useRef(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(open, wrap, close);
  const id = useId();
  const sel = options.find((o) => o.value === current);
  return (
    <span ref={wrap} className={cx('lg-popup-wrap', className)}>
      {label && <span id={id} className={cx('lg-field-label', TYPE[platform].body)}>{label}</span>}
      <span className="lg-dropdown">
        <button type="button" className={cx('lg-popup', 'lg-popup-' + platform, TYPE[platform].body)} style={{ width }} disabled={disabled}
          aria-haspopup="listbox" aria-expanded={open} aria-labelledby={label ? id : undefined} onClick={() => setOpen((o) => !o)}>
          <span className="lg-popup-value">{sel ? sel.label : ''}</span>
          <span className="lg-popup-glyph"><Icon name="chevron-up-down" size={platform === 'ios' ? 15 : 12} weight="semibold" /></span>
        </button>
        {open && (
          <Menu autoFocus onClose={close} width={menuWidth || width} className="lg-dropdown-menu"
            items={options.map((o) => ({ label: o.label, checked: o.value === current, disabled: o.disabled, onSelect: () => { setCurrent(o.value); close(); } }))} />
        )}
      </span>
    </span>
  );
}

/* ---------- Toggle (switch) ---------- */
/** On/off switch. iOS: only inside list rows; elsewhere use a toggle-style button. */
export function Toggle({ checked, defaultChecked = false, onChange, label, size = 'regular', disabled, platform: p, className, 'aria-label': ariaLabel }) {
  const platform = usePlatform(p);
  const [on, setOn] = useControlled(checked, defaultChecked, onChange);
  const id = useId();
  return (
    <span className={cx('lg-toggle-row', className)}>
      {label != null && <label htmlFor={id} className={cx('lg-toggle-label', TYPE[platform].body)}>{label}</label>}
      <button id={id} type="button" role="switch" aria-checked={!!on} disabled={disabled} aria-label={label == null ? ariaLabel : undefined}
        className={cx('lg-switch', 'lg-switch-' + platform, size === 'mini' && 'lg-switch-mini', on && 'lg-on')} onClick={() => setOn(!on)}>
        <span className="lg-switch-knob" />
      </button>
    </span>
  );
}

/* ---------- Checkbox ---------- */
/** macOS checkbox: on, off or mixed (a parent of differing subordinate checkboxes). */
export function Checkbox({ checked, defaultChecked = false, onChange, label, disabled, className }) {
  const platform = usePlatform();
  const [state, setState] = useControlled(checked, defaultChecked, onChange);
  const mixed = state === 'mixed';
  return (
    <button type="button" role="checkbox" aria-checked={mixed ? 'mixed' : !!state} disabled={disabled}
      className={cx('lg-check', (state === true || mixed) && 'lg-on', className)} onClick={() => setState(mixed ? true : !state)}>
      <span className="lg-check-box">{mixed ? <Icon name="minus" size={10} weight="bold" /> : state ? <Icon name="checkmark" size={10} weight="bold" /> : null}</span>
      {label != null && <span className={TYPE[platform].body}>{label}</span>}
    </button>
  );
}

/* ---------- RadioGroup ---------- */
/** Mutually exclusive choices, two to five of them. */
export function RadioGroup({ options = [], value, defaultValue, onChange, label, orientation = 'vertical', disabled, className }) {
  const platform = usePlatform();
  const [current, setCurrent] = useControlled(value, defaultValue, onChange);
  const refs = useRef([]);
  const id = useId();
  const enabled = options.filter((o) => !o.disabled);
  const move = (dir) => {
    const idx = enabled.findIndex((o) => o.value === current);
    const next = enabled[(idx + dir + enabled.length) % enabled.length];
    if (next) { setCurrent(next.value); const k = options.indexOf(next); if (refs.current[k]) refs.current[k].focus(); }
  };
  return (
    <div role="radiogroup" aria-labelledby={label ? id : undefined} className={cx('lg-radios', 'lg-radios-' + orientation, className)}
      onKeyDown={(e) => {
        if (e.key === 'ArrowDown' || e.key === 'ArrowRight') { e.preventDefault(); move(1); }
        if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') { e.preventDefault(); move(-1); }
      }}>
      {label && <span id={id} className={cx('lg-field-label', TYPE[platform].body)}>{label}</span>}
      {options.map((o, i) => {
        const sel = o.value === current;
        const tabbable = sel || (current === undefined && i === 0);
        return (
          <button key={o.value} ref={(el) => { refs.current[i] = el; }} type="button" role="radio" aria-checked={sel}
            tabIndex={tabbable ? 0 : -1} disabled={disabled || o.disabled} className={cx('lg-radio', sel && 'lg-on')} onClick={() => setCurrent(o.value)}>
            <span className="lg-radio-dot" />
            <span className={TYPE[platform].body}>{o.label}</span>
          </button>
        );
      })}
    </div>
  );
}

/* ---------- SegmentedControl ---------- */
/** A linear set of equal-width segments: pick one closely related view or option. */
export function SegmentedControl({ segments = [], value, defaultValue, onChange, momentary = false, fullWidth = false, size = 'regular', ariaLabel, className }) {
  const platform = usePlatform();
  const [current, setCurrent] = useControlled(value, defaultValue !== undefined ? defaultValue : segments[0] && segments[0].value, onChange);
  const index = segments.findIndex((s) => s.value === current);
  const n = segments.length || 1;
  return (
    <div role={momentary ? 'group' : 'radiogroup'} aria-label={ariaLabel}
      className={cx('lg-seg', 'lg-seg-' + platform, 'lg-seg-' + size, fullWidth && 'lg-seg-full', momentary && 'lg-seg-momentary', className)}
      style={{ gridTemplateColumns: 'repeat(' + n + ', 1fr)' }}
      onKeyDown={(e) => {
        if (momentary) return;
        const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
        if (d) { e.preventDefault(); const nx = segments[(index + d + n) % n]; setCurrent(nx.value); const b = e.currentTarget.querySelectorAll('button')[(index + d + n) % n]; if (b) b.focus(); }
      }}>
      {!momentary && index >= 0 && <span className="lg-seg-thumb" style={{ width: 'calc((100% - 4px) / ' + n + ')', transform: 'translateX(' + index * 100 + '%)' }} />}
      {segments.map((s, i) => {
        const sel = !momentary && i === index;
        return (
          <button key={s.value} type="button" role={momentary ? undefined : 'radio'} aria-checked={momentary ? undefined : sel}
            tabIndex={momentary || sel ? 0 : -1} aria-label={s.icon && !s.label ? s.ariaLabel || s.value : undefined} disabled={s.disabled}
            className={cx('lg-seg-btn', sel && 'lg-on', platform === 'ios' ? 'ios-subheadline' : 'mac-body')}
            onClick={() => (momentary ? onChange && onChange(s.value) : setCurrent(s.value))}>
            {s.icon ? <Icon name={s.icon} size={platform === 'ios' ? 17 : 14} weight="medium" /> : s.label}
          </button>
        );
      })}
    </div>
  );
}

/* ---------- Slider ---------- */
/** Choose a value from a continuous or stepped range; minimum leading, maximum trailing. */
export function Slider({ value, defaultValue = 50, min = 0, max = 100, step = 1, onChange, ticks = 0, minIcon, maxIcon, label, valueLabel, disabled, className }) {
  const platform = usePlatform();
  const [v, setV] = useControlled(value, defaultValue, onChange);
  const id = useId();
  const pct = ((v - min) / (max - min)) * 100;
  return (
    <div className={cx('lg-slider', 'lg-slider-' + platform, disabled && 'lg-disabled', className)}>
      {label && <label htmlFor={id} className={cx('lg-field-label', TYPE[platform].body)}>{label}</label>}
      <div className="lg-slider-row">
        {minIcon && <Icon name={minIcon} size={platform === 'ios' ? 17 : 13} className="lg-slider-end" />}
        <div className="lg-slider-track-wrap">
          <input id={id} type="range" min={min} max={max} step={step} value={v} disabled={disabled}
            aria-valuetext={valueLabel ? valueLabel(v) : undefined}
            onChange={(e) => setV(Number(e.target.value))} style={{ '--lg-pct': pct + '%' }} className="lg-range" />
          {ticks > 1 && (
            <div className="lg-ticks" aria-hidden="true">
              {Array.from({ length: ticks }, (_, i) => <i key={i} />)}
            </div>
          )}
        </div>
        {maxIcon && <Icon name={maxIcon} size={platform === 'ios' ? 17 : 13} className="lg-slider-end" />}
      </div>
    </div>
  );
}

/* ---------- Stepper ---------- */
/** Increase or decrease a value by a small increment; always shown beside the value it changes. */
export function Stepper({ value, defaultValue = 0, min = -Infinity, max = Infinity, step = 1, onChange, label, format = (x) => String(x), className }) {
  const platform = usePlatform();
  const [v, setV] = useControlled(value, defaultValue, onChange);
  const bump = (dir, e) => {
    const mult = platform === 'mac' && e && e.shiftKey ? 10 : 1;
    setV(Math.max(min, Math.min(max, v + dir * step * mult)));
  };
  const valueEl = <output className={cx('lg-stepper-value', TYPE[platform].body)} aria-live="polite">{format(v)}</output>;
  if (platform === 'ios') {
    return (
      <div className={cx('lg-stepper-row', className)}>
        {label && <span className={cx('lg-stepper-label', TYPE.ios.body)}>{label}</span>}
        {valueEl}
        <div className="lg-stepper-ios" role="group" aria-label={label}>
          <button type="button" aria-label="減少" disabled={v <= min} onClick={(e) => bump(-1, e)}><Icon name="minus" size={17} weight="semibold" /></button>
          <span className="lg-stepper-div" />
          <button type="button" aria-label="增加" disabled={v >= max} onClick={(e) => bump(1, e)}><Icon name="plus" size={17} weight="semibold" /></button>
        </div>
      </div>
    );
  }
  return (
    <div className={cx('lg-stepper-row', className)}>
      {label && <span className={cx('lg-stepper-label', TYPE.mac.body)}>{label}</span>}
      <span className="lg-stepper-field">{valueEl}</span>
      <div className="lg-stepper-mac" role="group" aria-label={label}>
        <button type="button" aria-label="增加" disabled={v >= max} onClick={(e) => bump(1, e)}><svg viewBox="0 0 10 6" aria-hidden="true"><path d="M1.5 5L5 1.5 8.5 5" /></svg></button>
        <button type="button" aria-label="減少" disabled={v <= min} onClick={(e) => bump(-1, e)}><svg viewBox="0 0 10 6" aria-hidden="true"><path d="M1.5 1L5 4.5 8.5 1" /></svg></button>
      </div>
    </div>
  );
}

/* ---------- TextField ---------- */
/** Small, specific text input with a label that stays when the placeholder disappears. */
export function TextField({ label, placeholder, value, defaultValue = '', onChange, secure = false, type = 'text', clearButton, error, hint, disabled, leadingIcon, width, className, ...rest }) {
  const platform = usePlatform();
  const [v, setV] = useControlled(value, defaultValue, onChange);
  const id = useId();
  const showClear = (clearButton !== undefined ? clearButton : platform === 'ios') && v && !disabled;
  const msgId = id + '-msg';
  return (
    <div className={cx('lg-field', 'lg-field-' + platform, error && 'lg-field-error', className)} style={{ width }}>
      {label && <label htmlFor={id} className={cx('lg-field-label', platform === 'ios' ? 'ios-footnote' : 'mac-body')}>{label}</label>}
      <div className="lg-field-box">
        {leadingIcon && <Icon name={leadingIcon} size={platform === 'ios' ? 17 : 13} className="lg-field-lead" />}
        <input id={id} className={TYPE[platform].body} type={secure ? 'password' : type} value={v} placeholder={placeholder} disabled={disabled}
          aria-invalid={!!error || undefined} aria-describedby={error || hint ? msgId : undefined} onChange={(e) => setV(e.target.value)} {...rest} />
        {showClear && (
          <button type="button" className="lg-field-clear" aria-label="清除文字" onClick={() => setV('')}>
            <span><Icon name="xmark" size={9} weight="bold" /></span>
          </button>
        )}
      </div>
      {error ? (
        <div id={msgId} className={cx('lg-field-msg', 'lg-field-msg-error', TYPE[platform].footnote)}><Icon name="exclamation-triangle" size={platform === 'ios' ? 14 : 11} weight="medium" />{error}</div>
      ) : hint ? <div id={msgId} className={cx('lg-field-msg', TYPE[platform].footnote)}>{hint}</div> : null}
    </div>
  );
}

/* ---------- SearchField ---------- */
/** Search a collection: placeholder says what's searchable, results update as people type. */
export function SearchField({ placeholder = '搜尋', value, defaultValue = '', onChange, onSubmit, tokens = [], onRemoveToken, scopes, scope, onScopeChange, glass = false, width, className }) {
  const platform = usePlatform();
  const [v, setV] = useControlled(value, defaultValue, onChange);
  const input = useRef(null);
  return (
    <div className={cx('lg-search-wrap', className)} style={{ width }}>
      <div role="search" className={cx('lg-search', 'lg-search-' + platform, glass && 'lg-glass lg-glass-regular lg-shape-capsule')} onClick={() => input.current && input.current.focus()}>
        <Icon name="magnifyingglass" size={platform === 'ios' ? 17 : 13} weight="medium" className="lg-search-glyph" />
        {tokens.map((t) => (
          <span key={t} className={cx('lg-token', TYPE[platform].sub)}>{t}
            {onRemoveToken && <button type="button" aria-label={'移除 ' + t} onClick={(e) => { e.stopPropagation(); onRemoveToken(t); }}><Icon name="xmark" size={9} weight="bold" /></button>}
          </span>
        ))}
        <input ref={input} type="search" className={TYPE[platform].body} value={v} placeholder={tokens.length ? '' : placeholder} aria-label={placeholder}
          onChange={(e) => setV(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && onSubmit) onSubmit(v); }} />
        {v && <button type="button" className="lg-field-clear" aria-label="清除搜尋" onClick={(e) => { e.stopPropagation(); setV(''); }}><span><Icon name="xmark" size={9} weight="bold" /></span></button>}
      </div>
      {scopes && scopes.length > 0 && (
        <SegmentedControl fullWidth ariaLabel="搜尋範圍" value={scope} defaultValue={scopes[0].value} onChange={onScopeChange} segments={scopes} className="lg-scope" />
      )}
    </div>
  );
}

/* ---------- Alert ---------- */
const orderAlert = (actions, stacked) => {
  const cancel = actions.filter((a) => a.role === 'cancel');
  const def = actions.filter((a) => a.role === 'default');
  const rest = actions.filter((a) => a.role !== 'cancel' && a.role !== 'default');
  return stacked ? [...def, ...rest, ...cancel] : [...cancel, ...rest, ...def];
};
/** Critical information that needs attention now; at most three buttons. */
export function Alert({ title, message, actions = [{ label: '好', role: 'default' }], icon, textField, suppression, presented = false, platform: p, className }) {
  const platform = usePlatform(p);
  const list = actions.slice(0, 3);
  const stacked = list.length > 2;
  const ordered = orderAlert(list, stacked);
  const id = useId();
  const card = (
    <div role="alertdialog" aria-modal={presented || undefined} aria-labelledby={id + 't'} aria-describedby={message ? id + 'm' : undefined}
      className={cx('lg-alert', 'lg-alert-' + platform, 'lg-glass', 'lg-glass-regular', className)}>
      {platform === 'mac' && icon && <div className="lg-alert-icon">{icon}</div>}
      <div id={id + 't'} className={cx('lg-alert-title', platform === 'ios' ? 'ios-headline' : 'mac-headline')}>{title}</div>
      {message && <div id={id + 'm'} className={cx('lg-alert-msg', platform === 'ios' ? 'ios-footnote' : 'mac-callout')}>{message}</div>}
      {textField && (
        <div className="lg-alert-field"><TextField placeholder={textField.placeholder} secure={textField.secure} clearButton={false} /></div>
      )}
      {suppression && platform === 'mac' && <div className="lg-alert-suppress"><Checkbox label={suppression} /></div>}
      <div className={cx('lg-alert-actions', stacked ? 'lg-stacked' : 'lg-row')}>
        {ordered.map((a, i) => (
          <Button key={i} platform={platform} size={platform === 'ios' ? 'large' : 'large'} variant={a.role === 'default' ? 'borderedProminent' : 'bordered'}
            role={a.role === 'destructive' ? 'destructive' : a.role === 'cancel' ? 'cancel' : 'normal'} disabled={a.disabled} onClick={a.onPress}
            className="lg-alert-btn" autoFocus={a.role === 'default' && presented}>
            {a.label}
          </Button>
        ))}
      </div>
    </div>
  );
  return presented ? <div className="lg-scrim">{card}</div> : card;
}

/* ---------- ActionSheet ---------- */
/** Choices that follow an action the person started (iOS confirmation dialog). */
export function ActionSheet({ title, message, actions = [], cancelLabel = '取消', onCancel, className }) {
  const destructive = actions.filter((a) => a.role === 'destructive');
  const others = actions.filter((a) => a.role !== 'destructive' && a.role !== 'cancel');
  return (
    <div role="dialog" aria-label={title || '選項'} className={cx('lg-sheet-actions', className)}>
      <div className="lg-as-group lg-glass lg-glass-regular">
        {(title || message) && (
          <div className="lg-as-head">
            {title && <div className="ios-footnote lg-as-title">{title}</div>}
            {message && <div className="ios-footnote lg-as-msg">{message}</div>}
          </div>
        )}
        {[...destructive, ...others].map((a, i) => (
          <button key={i} type="button" className={cx('lg-as-btn', 'ios-body', a.role === 'destructive' && 'lg-as-destructive')} disabled={a.disabled} onClick={a.onPress}>{a.label}</button>
        ))}
      </div>
      <div className="lg-as-group lg-glass lg-glass-regular">
        <button type="button" className="lg-as-btn lg-as-cancel ios-body-em" onClick={onCancel}>{cancelLabel}</button>
      </div>
    </div>
  );
}

/* ---------- Sheet ---------- */
/** A scoped task closely tied to the current context, with Cancel and Done. */
export function Sheet({ title, detent = 'large', grabber, cancelLabel = '取消', doneLabel = '完成', onCancel, onDone, doneDisabled, hideDone = false, symbols = true, height, platform: p, className, children }) {
  const platform = usePlatform(p);
  if (platform === 'mac') {
    return (
      <div role="dialog" aria-label={title} className={cx('lg-sheet', 'lg-sheet-mac', className)} style={{ height }}>
        {title && <div className="lg-sheet-mac-title mac-title-3">{title}</div>}
        <div className="lg-sheet-body">{children}</div>
        <div className="lg-sheet-mac-actions">
          <Button platform="mac" variant="bordered" role="cancel" onClick={onCancel}>{cancelLabel}</Button>
          {!hideDone && <Button platform="mac" variant="borderedProminent" disabled={doneDisabled} onClick={onDone}>{doneLabel}</Button>}
        </div>
      </div>
    );
  }
  const showGrabber = grabber !== undefined ? grabber : detent === 'medium';
  return (
    <div role="dialog" aria-label={title} className={cx('lg-sheet', 'lg-sheet-ios', 'lg-sheet-' + detent, className)} style={{ height }}>
      {showGrabber && <div className="lg-grabber" aria-hidden="true" />}
      <div className="lg-sheet-bar">
        {symbols ? <Button platform="ios" variant="glass" iconOnly icon="xmark" aria-label={cancelLabel} onClick={onCancel} />
          : <Button platform="ios" variant="glass" onClick={onCancel}>{cancelLabel}</Button>}
        <div className="lg-sheet-title ios-headline">{title}</div>
        {hideDone ? <span className="lg-sheet-spacer" /> : symbols
          ? <Button platform="ios" variant="glassProminent" iconOnly icon="checkmark" aria-label={doneLabel} disabled={doneDisabled} onClick={onDone} />
          : <Button platform="ios" variant="glassProminent" disabled={doneDisabled} onClick={onDone}>{doneLabel}</Button>}
      </div>
      <div className="lg-sheet-body">{children}</div>
    </div>
  );
}

/* ---------- Popover ---------- */
/** A transient view pointing at the control that revealed it. */
export function Popover({ arrow = 'top', width = 280, title, className, children }) {
  const platform = usePlatform();
  return (
    <div role="dialog" aria-label={title} className={cx('lg-popover', 'lg-arrow-' + arrow, className)} style={{ width }}>
      <span className="lg-popover-arrow lg-glass lg-glass-regular" aria-hidden="true" />
      <div className="lg-popover-card lg-glass lg-glass-regular">
        {title && <div className={cx('lg-popover-title', TYPE[platform].headline)}>{title}</div>}
        {children}
      </div>
    </div>
  );
}

/* ---------- List ---------- */
/** Rows of text-centric data, plain or in inset groups, with a header and footer. */
export function List({ appearance = 'insetGrouped', header, footer, alternating = false, className, children }) {
  const platform = usePlatform();
  return (
    <section className={cx('lg-list', 'lg-list-' + appearance, 'lg-list-' + platform, alternating && 'lg-list-alt', className)}>
      {header && <div className={cx('lg-list-header', platform === 'ios' ? 'ios-footnote' : 'mac-headline')}>{header}</div>}
      <div className="lg-list-body" role="list">{children}</div>
      {footer && <div className={cx('lg-list-footer', TYPE[platform].footnote)}>{footer}</div>}
    </section>
  );
}
/** One row of a List: optional icon, title, subtitle, trailing detail and accessory. */
export function ListRow({ title, subtitle, detail, icon, iconTint = 'blue', accessory = 'none', selected = false, destructive = false, disabled = false, onClick, href, className }) {
  const platform = usePlatform();
  const interactive = !!(onClick || href);
  const Tag = href ? 'a' : interactive ? 'button' : 'div';
  const acc = typeof accessory === 'string' ? (
    accessory === 'disclosure' ? <Icon name="chevron-right" size={platform === 'ios' ? 14 : 11} weight="semibold" className="lg-row-chev" />
      : accessory === 'checkmark' ? <Icon name="checkmark" size={platform === 'ios' ? 17 : 13} weight="semibold" className="lg-row-check" title="已選取" />
        : accessory === 'info' ? <Icon name="info" size={platform === 'ios' ? 22 : 15} className="lg-row-info" title="更多資訊" /> : null
  ) : accessory;
  return (
    <div role="listitem" className="lg-row-li">
      <Tag href={href} type={Tag === 'button' ? 'button' : undefined} onClick={onClick} disabled={Tag === 'button' ? disabled : undefined} aria-current={selected || undefined}
        className={cx('lg-row', interactive && 'lg-row-interactive', selected && 'lg-row-selected', destructive && 'lg-row-destructive', disabled && 'lg-row-disabled', className)}>
        {icon && <span className="lg-row-icon" style={{ background: tintVar(iconTint) }}><Icon name={icon} size={platform === 'ios' ? 18 : 13} weight="medium" /></span>}
        <span className="lg-row-text">
          <span className={cx('lg-row-title', TYPE[platform].body)}>{title}</span>
          {subtitle && <span className={cx('lg-row-sub', platform === 'ios' ? 'ios-subheadline' : 'mac-callout')}>{subtitle}</span>}
        </span>
        {detail != null && <span className={cx('lg-row-detail', TYPE[platform].body)}>{detail}</span>}
        {acc && <span className="lg-row-acc">{acc}</span>}
      </Tag>
    </div>
  );
}

/* ---------- TabBar ---------- */
/** Top-level navigation between app sections; floats on Liquid Glass. */
export function TabBar({ items = [], value, defaultValue, onChange, search, accessory, layout = 'compact', className }) {
  const [current, setCurrent] = useControlled(value, defaultValue !== undefined ? defaultValue : items[0] && items[0].value, onChange);
  return (
    <nav className={cx('lg-tabbar-wrap', 'lg-tabbar-' + layout, className)} aria-label="分頁">
      {accessory && <div className="lg-tab-accessory lg-glass lg-glass-regular lg-shape-capsule">{accessory}</div>}
      <div className="lg-tabbar-row">
        <div className="lg-tabbar lg-glass lg-glass-regular lg-shape-capsule" role="tablist">
          {items.map((it) => {
            const sel = it.value === current;
            return (
              <button key={it.value} type="button" role="tab" aria-selected={sel} className={cx('lg-tab', sel && 'lg-on')} onClick={() => setCurrent(it.value)}>
                <span className="lg-tab-icon">
                  <Icon name={it.icon} size={layout === 'compact' ? 24 : 18} weight={sel ? 'semibold' : 'medium'} />
                  {it.badge != null && <span className="lg-badge" aria-label={it.badge + ' 則新項目'}>{it.badge}</span>}
                </span>
                <span className="lg-tab-label">{it.label}</span>
              </button>
            );
          })}
        </div>
        {search && (
          <button type="button" role="tab" aria-selected={current === (search.value || 'search')} aria-label={search.label || '搜尋'}
            className={cx('lg-tab-search lg-glass lg-glass-regular lg-shape-circle', current === (search.value || 'search') && 'lg-on')} onClick={() => setCurrent(search.value || 'search')}>
            <Icon name="magnifyingglass" size={22} weight="medium" />
          </button>
        )}
      </div>
    </nav>
  );
}

/* ---------- Toolbar ---------- */
const ToolGroup = ({ group, platform }) => {
  const items = Array.isArray(group) ? group : [group];
  const prominent = items.filter((it) => it.prominent);
  const plain = items.filter((it) => !it.prominent);
  return (
    <>
      {plain.length > 0 && (
        <div className={cx('lg-tool-group', 'lg-glass', 'lg-glass-regular', 'lg-shape-capsule')} role="group">
          {plain.map((it, i) => it.node ? <React.Fragment key={i}>{it.node}</React.Fragment> : (
            <button key={i} type="button" title={it.label} aria-label={it.text ? undefined : it.label} disabled={it.disabled} onClick={it.onClick}
              className={cx('lg-tool-btn', it.text && 'lg-tool-text', it.text && TYPE[platform].body)}>
              {it.text ? it.label : <Icon name={it.icon} size={platform === 'ios' ? 19 : 15} weight="medium" />}
            </button>
          ))}
        </div>
      )}
      {prominent.map((it, i) => (
        <Button key={'p' + i} platform={platform} variant="glassProminent" size={platform === 'ios' ? 'large' : 'regular'} icon={it.text ? undefined : it.icon}
          iconOnly={!it.text} aria-label={it.text ? undefined : it.label} title={it.label} disabled={it.disabled} onClick={it.onClick} className="lg-tool-prominent">
          {it.text ? it.label : null}
        </Button>
      ))}
    </>
  );
};
/** Title, navigation and the most-used actions along the top of a window or view, in up to three groups. */
export function Toolbar({ title, subtitle, leading = [], center = [], trailing = [], largeTitle = false, edgeEffect = true, platform: p, className }) {
  const platform = usePlatform(p);
  return (
    <header className={cx('lg-toolbar', 'lg-toolbar-' + platform, edgeEffect && 'lg-toolbar-edge', className)}>
      <div className="lg-toolbar-row">
        <div className="lg-toolbar-zone lg-zone-leading">
          {leading.map((g, i) => <ToolGroup key={i} group={g} platform={platform} />)}
          {platform === 'mac' && title && (
            <div className="lg-toolbar-titles">
              <div className="mac-headline lg-toolbar-title">{title}</div>
              {subtitle && <div className="mac-callout lg-toolbar-sub">{subtitle}</div>}
            </div>
          )}
        </div>
        {platform === 'ios' && !largeTitle && title && <div className="lg-toolbar-center-title ios-headline">{title}</div>}
        {center.length > 0 && <div className="lg-toolbar-zone lg-zone-center">{center.map((g, i) => <ToolGroup key={i} group={g} platform={platform} />)}</div>}
        <div className="lg-toolbar-zone lg-zone-trailing">{trailing.map((g, i) => <ToolGroup key={i} group={g} platform={platform} />)}</div>
      </div>
      {platform === 'ios' && largeTitle && title && <h1 className="lg-large-title ios-large-title-em">{title}</h1>}
    </header>
  );
}

/* ---------- Sidebar ---------- */
/** Leading-edge navigation between app areas; floats on Liquid Glass. At most two levels. */
export function Sidebar({ sections = [], value, defaultValue, onChange, floating = true, width = 220, header, className }) {
  const platform = usePlatform();
  const first = sections[0] && sections[0].items[0];
  const [current, setCurrent] = useControlled(value, defaultValue !== undefined ? defaultValue : first && first.value, onChange);
  const [openGroups, setOpenGroups] = useState({});
  const renderItem = (it, depth) => {
    const sel = it.value === current;
    const hasKids = it.children && it.children.length > 0 && depth === 0;
    const open = openGroups[it.value] !== false;
    return (
      <li key={it.value}>
        <button type="button" aria-current={sel || undefined} aria-expanded={hasKids ? open : undefined}
          className={cx('lg-side-item', TYPE[platform].body, sel && 'lg-on', depth && 'lg-side-sub')} onClick={() => setCurrent(it.value)}>
          {hasKids ? (
            <span className={cx('lg-side-disc', open && 'lg-open')} role="presentation" onClick={(e) => { e.stopPropagation(); setOpenGroups((g) => ({ ...g, [it.value]: !open })); }}>
              <Icon name="chevron-right" size={10} weight="bold" />
            </span>
          ) : depth === 0 ? <span className="lg-side-disc-space" /> : null}
          {it.icon && <Icon name={it.icon} size={platform === 'ios' ? 20 : 15} weight="medium" className="lg-side-icon" />}
          <span className="lg-side-label">{it.label}</span>
          {it.badge != null && <span className={cx('lg-side-badge', TYPE[platform].callout)}>{it.badge}</span>}
        </button>
        {hasKids && open && <ul className="lg-side-list">{it.children.map((k) => renderItem(k, 1))}</ul>}
      </li>
    );
  };
  return (
    <nav aria-label="側邊欄" className={cx('lg-sidebar', 'lg-sidebar-' + platform, floating ? 'lg-glass lg-glass-regular lg-sidebar-floating' : 'lg-sidebar-inline', className)} style={{ width }}>
      {header && <div className="lg-side-top">{header}</div>}
      {sections.map((s, i) => (
        <div key={i} className="lg-side-section">
          {s.title && <div className={cx('lg-side-heading', platform === 'ios' ? 'ios-title-3' : 'mac-subheadline')}>{s.title}</div>}
          <ul className="lg-side-list">{s.items.map((it) => renderItem(it, 0))}</ul>
        </div>
      ))}
    </nav>
  );
}

/* ---------- WindowFrame ---------- */
/** A macOS window frame for layout mock-ups only — real apps use the system window. */
export function WindowFrame({ title, width = 760, height = 440, sidebar, toolbar, inactive = false, className, children }) {
  return (
    <PlatformContext.Provider value="mac">
      <div className={cx('lg-window', 'lg-mac', inactive && 'lg-window-inactive', className)} style={{ width, height }} aria-label={title} role="group">
        <div className="lg-traffic" aria-hidden="true"><i className="lg-tl-close" /><i className="lg-tl-min" /><i className="lg-tl-zoom" /></div>
        {sidebar && <div className="lg-window-sidebar">{sidebar}</div>}
        <div className="lg-window-main">
          {toolbar && <div className="lg-window-toolbar">{toolbar}</div>}
          <div className="lg-window-content">{children}</div>
        </div>
      </div>
    </PlatformContext.Provider>
  );
}

export { PlatformContext };

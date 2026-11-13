import type * as React from 'react';

export type Platform = 'mac' | 'ios';
export type IconName =
  | 'chevron-left' | 'chevron-right' | 'chevron-down' | 'chevron-up-down' | 'checkmark' | 'xmark' | 'plus' | 'minus'
  | 'magnifyingglass' | 'ellipsis' | 'sidebar' | 'share' | 'trash' | 'slider-horizontal' | 'house' | 'folder' | 'photo'
  | 'music-note' | 'person' | 'bell' | 'info' | 'exclamation-triangle' | 'star' | 'compose' | 'external-drive' | 'undo'
  | 'filter' | 'clock';
export type SystemTint = 'red' | 'orange' | 'yellow' | 'green' | 'mint' | 'teal' | 'cyan' | 'blue' | 'indigo' | 'purple' | 'pink' | 'brown'
  | 'gray-1' | 'gray-2' | 'gray-3';

/** The content layer: app content and background under the Liquid Glass layer. Sets the platform for its subtree. */
export interface ContentLayerProps { platform?: Platform; tone?: 'plain' | 'grouped' | 'window' | 'media'; padded?: boolean; className?: string; style?: React.CSSProperties; children?: React.ReactNode }
export declare function ContentLayer(props: ContentLayerProps): React.ReactElement;

/** Liquid Glass material for controls and navigation. Never for content. */
export interface GlassProps extends React.HTMLAttributes<HTMLElement> { variant?: 'regular' | 'clear'; shape?: 'capsule' | 'rounded' | 'rect' | 'circle'; dim?: boolean; interactive?: boolean; as?: keyof JSX.IntrinsicElements }
export declare function Glass(props: GlassProps): React.ReactElement;

/** Interface icon from the system's 24×24 set; decorative unless `title` is set. */
export interface IconProps { name: IconName; size?: number; weight?: 'regular' | 'medium' | 'semibold' | 'bold'; title?: string; className?: string; style?: React.CSSProperties }
export declare function Icon(props: IconProps): React.ReactElement | null;
export declare const iconNames: IconName[];

/** Initiates an instantaneous action. */
export interface ButtonProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'role'> {
  /** SwiftUI equivalents: .glass, .glassProminent, .bordered, .borderedProminent, .borderless */
  variant?: 'glass' | 'glassProminent' | 'bordered' | 'borderedProminent' | 'borderless';
  /** HIG button role. Primary = variant ending in Prominent; never make a destructive button primary. */
  role?: 'normal' | 'cancel' | 'destructive';
  size?: 'mini' | 'small' | 'regular' | 'large' | 'extraLarge';
  shape?: 'capsule' | 'roundedRectangle' | 'circle';
  icon?: IconName; iconOnly?: boolean; loading?: boolean; loadingLabel?: string; platform?: Platform;
}
export declare const Button: React.ForwardRefExoticComponent<ButtonProps & React.RefAttributes<HTMLButtonElement>>;

export interface MenuItem { label?: React.ReactNode; icon?: IconName; shortcut?: string; checked?: boolean; disabled?: boolean; destructive?: boolean; submenu?: boolean; separator?: boolean; header?: string; onSelect?: (item: MenuItem) => void; value?: string }
/** A menu panel of commands, options or states. */
export interface MenuProps { items: MenuItem[]; onSelect?: (item: MenuItem) => void; onClose?: () => void; width?: number; autoFocus?: boolean; platform?: Platform; className?: string; style?: React.CSSProperties }
export declare function Menu(props: MenuProps): React.ReactElement;

/** A button that reveals a menu of actions. */
export interface PullDownButtonProps { label: string; icon?: IconName; items: MenuItem[]; variant?: ButtonProps['variant']; size?: ButtonProps['size']; iconOnly?: boolean; disabled?: boolean; menuWidth?: number; align?: 'start' | 'end'; className?: string }
export declare function PullDownButton(props: PullDownButtonProps): React.ReactElement;

export interface Option { value: string; label: string; disabled?: boolean }
/** Shows the current choice among mutually exclusive options. */
export interface PopUpButtonProps { options: Option[]; value?: string; defaultValue?: string; onChange?: (value: string) => void; label?: string; disabled?: boolean; width?: number; menuWidth?: number; className?: string }
export declare function PopUpButton(props: PopUpButtonProps): React.ReactElement;

/** On/off switch. */
export interface ToggleProps { checked?: boolean; defaultChecked?: boolean; onChange?: (on: boolean) => void; label?: React.ReactNode; size?: 'regular' | 'mini'; disabled?: boolean; platform?: Platform; className?: string; 'aria-label'?: string }
export declare function Toggle(props: ToggleProps): React.ReactElement;

/** macOS checkbox with a mixed state. */
export interface CheckboxProps { checked?: boolean | 'mixed'; defaultChecked?: boolean | 'mixed'; onChange?: (checked: boolean | 'mixed') => void; label?: React.ReactNode; disabled?: boolean; className?: string }
export declare function Checkbox(props: CheckboxProps): React.ReactElement;

/** Two to five mutually exclusive choices. */
export interface RadioGroupProps { options: Option[]; value?: string; defaultValue?: string; onChange?: (value: string) => void; label?: string; orientation?: 'vertical' | 'horizontal'; disabled?: boolean; className?: string }
export declare function RadioGroup(props: RadioGroupProps): React.ReactElement;

export interface Segment { value: string; label?: string; icon?: IconName; ariaLabel?: string; disabled?: boolean }
/** Equal-width segments; text or icons, never both. */
export interface SegmentedControlProps { segments: Segment[]; value?: string; defaultValue?: string; onChange?: (value: string) => void; momentary?: boolean; fullWidth?: boolean; size?: 'small' | 'regular'; ariaLabel?: string; className?: string }
export declare function SegmentedControl(props: SegmentedControlProps): React.ReactElement;

/** A value from a range; minimum leading, maximum trailing. */
export interface SliderProps { value?: number; defaultValue?: number; min?: number; max?: number; step?: number; onChange?: (value: number) => void; ticks?: number; minIcon?: IconName; maxIcon?: IconName; label?: string; valueLabel?: (value: number) => string; disabled?: boolean; className?: string }
export declare function Slider(props: SliderProps): React.ReactElement;

/** Increment / decrement beside the value it changes. */
export interface StepperProps { value?: number; defaultValue?: number; min?: number; max?: number; step?: number; onChange?: (value: number) => void; label?: string; format?: (value: number) => string; className?: string }
export declare function Stepper(props: StepperProps): React.ReactElement;

/** Single-line text entry with a persistent label. */
export interface TextFieldProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'value' | 'defaultValue'> {
  label?: string; placeholder?: string; value?: string; defaultValue?: string; onChange?: (value: string) => void; secure?: boolean;
  clearButton?: boolean; error?: string; hint?: string; leadingIcon?: IconName; width?: number | string;
}
export declare function TextField(props: TextFieldProps): React.ReactElement;

/** Search field with optional tokens and scope bar. */
export interface SearchFieldProps { placeholder?: string; value?: string; defaultValue?: string; onChange?: (value: string) => void; onSubmit?: (value: string) => void; tokens?: string[]; onRemoveToken?: (token: string) => void; scopes?: Segment[]; scope?: string; onScopeChange?: (value: string) => void; glass?: boolean; width?: number | string; className?: string }
export declare function SearchField(props: SearchFieldProps): React.ReactElement;

/** Determinate bar / ring (value 0–1) or indeterminate spinner / bar (no value). */
export interface ProgressIndicatorProps { kind?: 'bar' | 'circular' | 'spinner'; value?: number; label?: string; size?: 'small' | 'regular' | 'large'; className?: string }
export declare function ProgressIndicator(props: ProgressIndicatorProps): React.ReactElement;

export interface AlertAction { label: string; role?: 'default' | 'cancel' | 'destructive'; onPress?: () => void; disabled?: boolean }
/** Critical information; up to three buttons, ordered by the HIG automatically. */
export interface AlertProps { title: string; message?: string; actions?: AlertAction[]; icon?: React.ReactNode; textField?: { placeholder?: string; secure?: boolean }; suppression?: string; presented?: boolean; platform?: Platform; className?: string }
export declare function Alert(props: AlertProps): React.ReactElement;

/** iOS confirmation dialog for choices after a deliberate action. */
export interface ActionSheetProps { title?: string; message?: string; actions: AlertAction[]; cancelLabel?: string; onCancel?: () => void; className?: string }
export declare function ActionSheet(props: ActionSheetProps): React.ReactElement;

/** A scoped task in the current context, with Cancel and Done. */
export interface SheetProps { title?: string; detent?: 'medium' | 'large'; grabber?: boolean; cancelLabel?: string; doneLabel?: string; onCancel?: () => void; onDone?: () => void; doneDisabled?: boolean; hideDone?: boolean; symbols?: boolean; height?: number | string; platform?: Platform; className?: string; children?: React.ReactNode }
export declare function Sheet(props: SheetProps): React.ReactElement;

/** A transient view that points at its source control. */
export interface PopoverProps { arrow?: 'top' | 'bottom' | 'leading' | 'trailing' | 'none'; width?: number; title?: string; className?: string; children?: React.ReactNode }
export declare function Popover(props: PopoverProps): React.ReactElement;

/** Rows of data, plain or in inset groups. */
export interface ListProps { appearance?: 'insetGrouped' | 'plain'; header?: React.ReactNode; footer?: React.ReactNode; alternating?: boolean; className?: string; children?: React.ReactNode }
export declare function List(props: ListProps): React.ReactElement;
/** A List row. */
export interface ListRowProps { title: React.ReactNode; subtitle?: React.ReactNode; detail?: React.ReactNode; icon?: IconName; iconTint?: SystemTint; accessory?: 'none' | 'disclosure' | 'checkmark' | 'info' | React.ReactNode; selected?: boolean; destructive?: boolean; disabled?: boolean; onClick?: () => void; href?: string; className?: string }
export declare function ListRow(props: ListRowProps): React.ReactElement;

export interface TabItem { value: string; label: string; icon: IconName; badge?: number | string }
/** Top-level navigation on a floating glass bar. */
export interface TabBarProps { items: TabItem[]; value?: string; defaultValue?: string; onChange?: (value: string) => void; search?: { label?: string; value?: string }; accessory?: React.ReactNode; layout?: 'compact' | 'regular'; className?: string }
export declare function TabBar(props: TabBarProps): React.ReactElement;

export interface ToolbarItem { icon?: IconName; label: string; onClick?: () => void; prominent?: boolean; text?: boolean; disabled?: boolean; node?: React.ReactNode }
/** Title, navigation and actions in leading / center / trailing zones; each inner array is one glass group. */
export interface ToolbarProps { title?: string; subtitle?: string; leading?: ToolbarItem[][]; center?: ToolbarItem[][]; trailing?: ToolbarItem[][]; largeTitle?: boolean; edgeEffect?: boolean; platform?: Platform; className?: string }
export declare function Toolbar(props: ToolbarProps): React.ReactElement;

export interface SidebarItem { value: string; label: string; icon?: IconName; badge?: number | string; children?: SidebarItem[] }
/** Leading-edge navigation; at most two levels. */
export interface SidebarProps { sections: { title?: string; items: SidebarItem[] }[]; value?: string; defaultValue?: string; onChange?: (value: string) => void; floating?: boolean; width?: number; header?: React.ReactNode; className?: string }
export declare function Sidebar(props: SidebarProps): React.ReactElement;

/** macOS window frame for layout mock-ups only. */
export interface WindowFrameProps { title?: string; width?: number; height?: number; sidebar?: React.ReactNode; toolbar?: React.ReactNode; inactive?: boolean; className?: string; children?: React.ReactNode }
export declare function WindowFrame(props: WindowFrameProps): React.ReactElement;

declare global {
  interface Window {
    LiquidGlass: {
      ContentLayer: typeof ContentLayer; Glass: typeof Glass; Icon: typeof Icon; iconNames: typeof iconNames; Button: typeof Button;
      PullDownButton: typeof PullDownButton; PopUpButton: typeof PopUpButton; Menu: typeof Menu; Toggle: typeof Toggle; Checkbox: typeof Checkbox;
      RadioGroup: typeof RadioGroup; SegmentedControl: typeof SegmentedControl; Slider: typeof Slider; Stepper: typeof Stepper; TextField: typeof TextField;
      SearchField: typeof SearchField; ProgressIndicator: typeof ProgressIndicator; Alert: typeof Alert; ActionSheet: typeof ActionSheet; Sheet: typeof Sheet;
      Popover: typeof Popover; List: typeof List; ListRow: typeof ListRow; TabBar: typeof TabBar; Toolbar: typeof Toolbar; Sidebar: typeof Sidebar; WindowFrame: typeof WindowFrame;
    };
  }
}

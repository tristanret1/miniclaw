/** Undo / redo command history for the editor. */

const MAX_HISTORY = 100;

export interface EditorCommand {
  execute(): void;
  undo(): void;
  readonly description: string;
}

export type ChangeCallback = () => void;

export class CommandHistory {
  private undoStack: EditorCommand[] = [];
  private redoStack: EditorCommand[] = [];
  private _onChange: ChangeCallback | null = null;

  /** Register a callback invoked after every execute/undo/redo. */
  get onChange(): ChangeCallback | null {
    return this._onChange;
  }

  set onChange(cb: ChangeCallback | null) {
    this._onChange = cb;
  }

  /** Execute a command and push it onto the undo stack. */
  execute(cmd: EditorCommand): void {
    cmd.execute();
    this.undoStack.push(cmd);
    // Executing a new command invalidates the redo stack.
    this.redoStack.length = 0;
    // Trim to limit.
    if (this.undoStack.length > MAX_HISTORY) {
      this.undoStack.shift();
    }
    this._onChange?.();
  }

  /** Undo the most recent command. */
  undo(): void {
    const cmd = this.undoStack.pop();
    if (!cmd) return;
    cmd.undo();
    this.redoStack.push(cmd);
    this._onChange?.();
  }

  /** Redo the most recently undone command. */
  redo(): void {
    const cmd = this.redoStack.pop();
    if (!cmd) return;
    cmd.execute();
    this.undoStack.push(cmd);
    this._onChange?.();
  }

  canUndo(): boolean {
    return this.undoStack.length > 0;
  }

  canRedo(): boolean {
    return this.redoStack.length > 0;
  }

  /** Clear all history. */
  clear(): void {
    this.undoStack.length = 0;
    this.redoStack.length = 0;
    this._onChange?.();
  }
}

import './PatchDiffViewer.css';

interface PatchDiffViewerProps {
  patch: string;
}

function classifyLine(line: string): string {
  if (line.startsWith('+++') || line.startsWith('---')) return 'patch-diff__line patch-diff__line--file';
  if (line.startsWith('+')) return 'patch-diff__line patch-diff__line--add';
  if (line.startsWith('-')) return 'patch-diff__line patch-diff__line--del';
  if (line.startsWith('@@')) return 'patch-diff__line patch-diff__line--hunk';
  if (line.startsWith('diff --git')) return 'patch-diff__line patch-diff__line--file';
  return 'patch-diff__line';
}

export function PatchDiffViewer({ patch }: PatchDiffViewerProps) {
  if (!patch || !patch.trim()) {
    return (
      <div className="patch-diff">
        <div className="patch-diff__header">Patch</div>
        <div className="patch-diff__empty">No patch generated</div>
      </div>
    );
  }

  const lines = patch.split('\n');

  return (
    <div className="patch-diff">
      <div className="patch-diff__header">Patch</div>
      <div className="patch-diff__content">
        {lines.map((line, i) => (
          <div key={i} className={classifyLine(line)}>
            {line || '\u00A0'}
          </div>
        ))}
      </div>
    </div>
  );
}

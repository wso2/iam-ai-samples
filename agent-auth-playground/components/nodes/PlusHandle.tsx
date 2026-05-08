import { Handle, Position } from 'reactflow';

interface PlusHandleProps {
  type: 'source' | 'target';
  position: Position;
  id?: string;
  connected?: boolean;
  alwaysShow?: boolean;
}

export default function PlusHandle({ type, position, id, connected = false, alwaysShow = false }: PlusHandleProps) {
  const showPlus = !connected || alwaysShow;

  if (!showPlus) {
    return <Handle type={type} position={position} id={id} />;
  }

  return (
    <Handle
      type={type}
      position={position}
      id={id}
      style={{
        width: 15,
        height: 15,
        background: 'white',
        border: '2px solid #000',
        borderRadius: '50%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'crosshair',
        boxShadow: '0 1px 4px rgba(0,0,0,0.2)',
      }}
    >
      <span
        style={{
          fontSize: 13,
          fontWeight: 700,
          color: '#000',
          lineHeight: 1,
          pointerEvents: 'none',
          userSelect: 'none',
          marginTop: -1,
        }}
      >
        +
      </span>
    </Handle>
  );
}

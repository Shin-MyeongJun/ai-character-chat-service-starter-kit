import type { ButtonHTMLAttributes, InputHTMLAttributes, SelectHTMLAttributes } from "react";
import { statuses, type GenerationStatus } from "@/lib/contracts";
export function Button({ variant = "secondary", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" }) {
  return <button className={`button ${variant} ${className}`} {...props} />;
}
export function Input(props: InputHTMLAttributes<HTMLInputElement>) { return <input className="input" {...props} />; }
export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) { return <select className="input" {...props} />; }
export function Badge({ status, recorded }: { status?: string; recorded?: boolean }) {
  const label = status ? Object.hasOwn(statuses, status) ? statuses[status as GenerationStatus] : status : recorded ? "저장됨" : "미기록";
  return <span className={`badge ${status ?? "neutral"}`} title={status === "stale" ? "생성 버전 변경 또는 실행 유효성 만료로 결과가 반영되지 않은 상태" : undefined}>{label}</span>;
}
export function Brand() { return <div className="brand"><span className="brand-mark" aria-hidden="true">S</span><span>STUDIO ADMIN</span></div>; }

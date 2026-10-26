module.exports = [
"[project]/apps/web/app/login/page.tsx [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "default",
    ()=>LoginPage
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/.pnpm/next@16.3.3_@babel+core@7.2_0274fc7c257f8100e4ae262111c874d1/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react-jsx-dev-runtime.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$client$2f$app$2d$dir$2f$link$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/.pnpm/next@16.3.3_@babel+core@7.2_0274fc7c257f8100e4ae262111c874d1/node_modules/next/dist/client/app-dir/link.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/.pnpm/next@16.3.3_@babel+core@7.2_0274fc7c257f8100e4ae262111c874d1/node_modules/next/navigation.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/.pnpm/next@16.3.3_@babel+core@7.2_0274fc7c257f8100e4ae262111c874d1/node_modules/next/dist/server/route-modules/app-page/vendored/ssr/react.js [app-ssr] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$lucide$2d$react$40$0$2e$468$2e$0_react$40$19$2e$2$2e$8$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$arrow$2d$right$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__ArrowRight$3e$__ = __turbopack_context__.i("[project]/node_modules/.pnpm/lucide-react@0.468.0_react@19.2.8/node_modules/lucide-react/dist/esm/icons/arrow-right.js [app-ssr] (ecmascript) <export default as ArrowRight>");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$lucide$2d$react$40$0$2e$468$2e$0_react$40$19$2e$2$2e$8$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$lock$2d$keyhole$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__LockKeyhole$3e$__ = __turbopack_context__.i("[project]/node_modules/.pnpm/lucide-react@0.468.0_react@19.2.8/node_modules/lucide-react/dist/esm/icons/lock-keyhole.js [app-ssr] (ecmascript) <export default as LockKeyhole>");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$lucide$2d$react$40$0$2e$468$2e$0_react$40$19$2e$2$2e$8$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$mail$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__Mail$3e$__ = __turbopack_context__.i("[project]/node_modules/.pnpm/lucide-react@0.468.0_react@19.2.8/node_modules/lucide-react/dist/esm/icons/mail.js [app-ssr] (ecmascript) <export default as Mail>");
var __TURBOPACK__imported__module__$5b$project$5d2f$apps$2f$web$2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/apps/web/lib/api.ts [app-ssr] (ecmascript)");
"use client";
;
;
;
;
;
;
function LoginForm() {
    const router = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useRouter"])();
    const params = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$navigation$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useSearchParams"])();
    const [email, setEmail] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [password, setPassword] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])("");
    const [busy, setBusy] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(false);
    const [error, setError] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["useState"])(null);
    async function submit(event) {
        event.preventDefault();
        setBusy(true);
        setError(null);
        try {
            await (0, __TURBOPACK__imported__module__$5b$project$5d2f$apps$2f$web$2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["login"])(email, password);
            const destination = params.get("next") ?? "/";
            router.replace(destination.startsWith("/") && !destination.startsWith("//") ? destination : "/");
        } catch (cause) {
            setError(cause instanceof __TURBOPACK__imported__module__$5b$project$5d2f$apps$2f$web$2f$lib$2f$api$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["ApiError"] && cause.code === "invalid_credentials" ? "이메일과 비밀번호를 확인해 주세요." : "로그인할 수 없어요. API 연결과 인증 설정을 확인해 주세요.");
        } finally{
            setBusy(false);
        }
    }
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("main", {
        id: "user-content",
        tabIndex: -1,
        className: "auth-page login-page",
        children: [
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "auth-art",
                children: [
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                        children: "✳"
                    }, void 0, false, {
                        fileName: "[project]/apps/web/app/login/page.tsx",
                        lineNumber: 26,
                        columnNumber: 107
                    }, this),
                    /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                        children: [
                            "모든 이야기는",
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("br", {}, void 0, false, {
                                fileName: "[project]/apps/web/app/login/page.tsx",
                                lineNumber: 26,
                                columnNumber: 131
                            }, this),
                            "당신이 돌아오기를",
                            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("br", {}, void 0, false, {
                                fileName: "[project]/apps/web/app/login/page.tsx",
                                lineNumber: 26,
                                columnNumber: 146
                            }, this),
                            "기다리고 있어요."
                        ]
                    }, void 0, true, {
                        fileName: "[project]/apps/web/app/login/page.tsx",
                        lineNumber: 26,
                        columnNumber: 121
                    }, this)
                ]
            }, void 0, true, {
                fileName: "[project]/apps/web/app/login/page.tsx",
                lineNumber: 26,
                columnNumber: 81
            }, this),
            /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                className: "auth-form-wrap",
                children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("form", {
                    className: "auth-form",
                    onSubmit: submit,
                    children: [
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                            className: "section-kicker",
                            children: "WELCOME BACK"
                        }, void 0, false, {
                            fileName: "[project]/apps/web/app/login/page.tsx",
                            lineNumber: 26,
                            columnNumber: 249
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("h1", {
                            children: "다시 오셨군요."
                        }, void 0, false, {
                            fileName: "[project]/apps/web/app/login/page.tsx",
                            lineNumber: 26,
                            columnNumber: 301
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                            children: "계속하고 싶은 이야기가 기다리고 있어요."
                        }, void 0, false, {
                            fileName: "[project]/apps/web/app/login/page.tsx",
                            lineNumber: 26,
                            columnNumber: 318
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                    children: "이메일"
                                }, void 0, false, {
                                    fileName: "[project]/apps/web/app/login/page.tsx",
                                    lineNumber: 26,
                                    columnNumber: 354
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "field",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$lucide$2d$react$40$0$2e$468$2e$0_react$40$19$2e$2$2e$8$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$mail$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__Mail$3e$__["Mail"], {
                                            size: 19
                                        }, void 0, false, {
                                            fileName: "[project]/apps/web/app/login/page.tsx",
                                            lineNumber: 26,
                                            columnNumber: 393
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                            type: "email",
                                            required: true,
                                            autoComplete: "email",
                                            value: email,
                                            onChange: (event)=>setEmail(event.target.value),
                                            placeholder: "you@example.com"
                                        }, void 0, false, {
                                            fileName: "[project]/apps/web/app/login/page.tsx",
                                            lineNumber: 26,
                                            columnNumber: 411
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/apps/web/app/login/page.tsx",
                                    lineNumber: 26,
                                    columnNumber: 370
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/apps/web/app/login/page.tsx",
                            lineNumber: 26,
                            columnNumber: 347
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("label", {
                            children: [
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("span", {
                                    children: "비밀번호"
                                }, void 0, false, {
                                    fileName: "[project]/apps/web/app/login/page.tsx",
                                    lineNumber: 26,
                                    columnNumber: 579
                                }, this),
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("div", {
                                    className: "field",
                                    children: [
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$lucide$2d$react$40$0$2e$468$2e$0_react$40$19$2e$2$2e$8$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$lock$2d$keyhole$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__LockKeyhole$3e$__["LockKeyhole"], {
                                            size: 19
                                        }, void 0, false, {
                                            fileName: "[project]/apps/web/app/login/page.tsx",
                                            lineNumber: 26,
                                            columnNumber: 619
                                        }, this),
                                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("input", {
                                            type: "password",
                                            required: true,
                                            autoComplete: "current-password",
                                            value: password,
                                            onChange: (event)=>setPassword(event.target.value),
                                            placeholder: "비밀번호"
                                        }, void 0, false, {
                                            fileName: "[project]/apps/web/app/login/page.tsx",
                                            lineNumber: 26,
                                            columnNumber: 644
                                        }, this)
                                    ]
                                }, void 0, true, {
                                    fileName: "[project]/apps/web/app/login/page.tsx",
                                    lineNumber: 26,
                                    columnNumber: 596
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/apps/web/app/login/page.tsx",
                            lineNumber: 26,
                            columnNumber: 572
                        }, this),
                        error && /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("p", {
                            className: "inline-notice",
                            role: "alert",
                            children: error
                        }, void 0, false, {
                            fileName: "[project]/apps/web/app/login/page.tsx",
                            lineNumber: 26,
                            columnNumber: 824
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])("button", {
                            className: "button button-primary",
                            disabled: busy,
                            type: "submit",
                            children: [
                                busy ? "로그인 중..." : "로그인",
                                /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$lucide$2d$react$40$0$2e$468$2e$0_react$40$19$2e$2$2e$8$2f$node_modules$2f$lucide$2d$react$2f$dist$2f$esm$2f$icons$2f$arrow$2d$right$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__$3c$export__default__as__ArrowRight$3e$__["ArrowRight"], {
                                    size: 18
                                }, void 0, false, {
                                    fileName: "[project]/apps/web/app/login/page.tsx",
                                    lineNumber: 26,
                                    columnNumber: 977
                                }, this)
                            ]
                        }, void 0, true, {
                            fileName: "[project]/apps/web/app/login/page.tsx",
                            lineNumber: 26,
                            columnNumber: 878
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$client$2f$app$2d$dir$2f$link$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["default"], {
                            className: "text-link",
                            href: "/register",
                            children: "새 계정 만들기"
                        }, void 0, false, {
                            fileName: "[project]/apps/web/app/login/page.tsx",
                            lineNumber: 26,
                            columnNumber: 1010
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$client$2f$app$2d$dir$2f$link$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["default"], {
                            className: "text-link",
                            href: "/forgot-password",
                            children: "비밀번호를 잊으셨나요?"
                        }, void 0, false, {
                            fileName: "[project]/apps/web/app/login/page.tsx",
                            lineNumber: 26,
                            columnNumber: 1070
                        }, this),
                        /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$client$2f$app$2d$dir$2f$link$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["default"], {
                            className: "text-link",
                            href: "/",
                            children: "홈으로 돌아가기"
                        }, void 0, false, {
                            fileName: "[project]/apps/web/app/login/page.tsx",
                            lineNumber: 26,
                            columnNumber: 1141
                        }, this)
                    ]
                }, void 0, true, {
                    fileName: "[project]/apps/web/app/login/page.tsx",
                    lineNumber: 26,
                    columnNumber: 203
                }, this)
            }, void 0, false, {
                fileName: "[project]/apps/web/app/login/page.tsx",
                lineNumber: 26,
                columnNumber: 171
            }, this)
        ]
    }, void 0, true, {
        fileName: "[project]/apps/web/app/login/page.tsx",
        lineNumber: 26,
        columnNumber: 10
    }, this);
}
function LoginPage() {
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(__TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["Suspense"], {
        children: /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f2e$pnpm$2f$next$40$16$2e$3$2e$3_$40$babel$2b$core$40$7$2e$2_0274fc7c257f8100e4ae262111c874d1$2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$ssr$2f$react$2d$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["jsxDEV"])(LoginForm, {}, void 0, false, {
            fileName: "[project]/apps/web/app/login/page.tsx",
            lineNumber: 29,
            columnNumber: 56
        }, this)
    }, void 0, false, {
        fileName: "[project]/apps/web/app/login/page.tsx",
        lineNumber: 29,
        columnNumber: 46
    }, this);
}
}),
"[project]/apps/web/lib/api.ts [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "ApiError",
    ()=>ApiError,
    "createMessage",
    ()=>createMessage,
    "generateAnswer",
    ()=>generateAnswer,
    "getConversationStart",
    ()=>getConversationStart,
    "getCreditBalance",
    ()=>getCreditBalance,
    "getCsrf",
    ()=>getCsrf,
    "getMe",
    ()=>getMe,
    "getPublishedWork",
    ()=>getPublishedWork,
    "listCatalog",
    ()=>listCatalog,
    "listCatalogTags",
    ()=>listCatalogTags,
    "listConversationMessages",
    ()=>listConversationMessages,
    "listMessages",
    ()=>listMessages,
    "listOwnedConversations",
    ()=>listOwnedConversations,
    "login",
    ()=>login,
    "logout",
    ()=>logout,
    "register",
    ()=>register,
    "request",
    ()=>request,
    "requestPasswordReset",
    ()=>requestPasswordReset,
    "resendVerification",
    ()=>resendVerification,
    "resetPassword",
    ()=>resetPassword,
    "startConversation",
    ()=>startConversation,
    "verifyEmail",
    ()=>verifyEmail
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$apps$2f$web$2f$lib$2f$recent$2d$chats$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/apps/web/lib/recent-chats.ts [app-ssr] (ecmascript)");
;
class ApiError extends Error {
    status;
    code;
    constructor(status, code, message){
        super(message), this.status = status, this.code = code;
        this.name = "ApiError";
    }
}
let csrfToken = null;
let csrfPromise = null;
let refreshPromise = null;
const REFRESH_UNCERTAIN_KEY = "moseori_refresh_uncertain";
async function getCsrf() {
    if (csrfToken) return csrfToken;
    csrfPromise ??= request("/auth/csrf").then((value)=>value.csrf_token);
    try {
        csrfToken = await csrfPromise;
        return csrfToken;
    } finally{
        csrfPromise = null;
    }
}
async function send(path, options = {}, recoverCsrf = true) {
    const method = (options.method ?? "GET").toUpperCase();
    const headers = new Headers(options.headers);
    if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    if (![
        "GET",
        "HEAD"
    ].includes(method)) headers.set("X-CSRF-Token", await getCsrf());
    const response = await fetch(`/backend${path}`, {
        ...options,
        headers,
        credentials: "include",
        cache: "no-store"
    });
    if (!response.ok) {
        let detail;
        try {
            detail = await response.json();
        } catch  {
            detail = null;
        }
        // The answer endpoint returns a typed generation result for completed failures.
        // Keep its retryable flag so the chat can offer a new attempt for the saved message.
        if (path.endsWith("/answers") && detail && typeof detail === "object" && "generation_id" in detail && "status" in detail) {
            return detail;
        }
        const payload = detail;
        const code = payload?.error?.code ?? payload?.error_code ?? (typeof payload?.detail === "object" ? payload.detail?.code : undefined) ?? `http_${response.status}`;
        const message = typeof payload?.detail === "string" ? payload.detail : code;
        if (code === "csrf_failed") {
            // The server rejected this request before executing the mutation.
            csrfToken = null;
            if (recoverCsrf) return send(path, options, false);
        }
        throw new ApiError(response.status, code, message);
    }
    if (response.status === 204) return undefined;
    return response.json();
}
async function refreshSession() {
    if (refreshPromise) return refreshPromise;
    refreshPromise = (async ()=>{
        // Refresh tokens rotate on every use. A per-tab promise alone is unsafe.
        if (typeof navigator === "undefined" || !navigator.locks) {
            throw new ApiError(401, "session_refresh_unavailable", "다시 로그인해 주세요.");
        }
        await navigator.locks.request("moseori-auth-refresh", async ()=>{
            // Another tab/request may already have refreshed while we waited.
            try {
                await send("/auth/me");
                return;
            } catch (cause) {
                if (!(cause instanceof ApiError) || cause.status !== 401 || cause.code !== "invalid_token") throw cause;
            }
            if (localStorage.getItem(REFRESH_UNCERTAIN_KEY)) {
                throw new ApiError(401, "refresh_uncertain", "갱신 결과를 확인할 수 없어 다시 로그인이 필요합니다.");
            }
            // Persist before sending: a closed tab or lost response must not replay
            // an old refresh token and revoke an otherwise valid token family.
            localStorage.setItem(REFRESH_UNCERTAIN_KEY, "1");
            try {
                await send("/auth/refresh", {
                    method: "POST"
                });
                localStorage.removeItem(REFRESH_UNCERTAIN_KEY);
            } catch (cause) {
                if (cause instanceof ApiError && cause.status < 500) localStorage.removeItem(REFRESH_UNCERTAIN_KEY);
                throw cause;
            }
        });
    })();
    try {
        await refreshPromise;
    } finally{
        refreshPromise = null;
    }
}
async function request(path, options = {}) {
    try {
        return await send(path, options);
    } catch (cause) {
        // Credential errors and invalid/revoked sessions are not access expiry.
        if (cause instanceof ApiError && cause.status === 401 && cause.code === "invalid_token" && (!path.startsWith("/auth/") || path === "/auth/me")) {
            try {
                await refreshSession();
                return await send(path, options);
            } catch (refreshError) {
                (0, __TURBOPACK__imported__module__$5b$project$5d2f$apps$2f$web$2f$lib$2f$recent$2d$chats$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["setRecentChatOwner"])(null);
                throw refreshError;
            }
        }
        if (cause instanceof ApiError && cause.status === 401) (0, __TURBOPACK__imported__module__$5b$project$5d2f$apps$2f$web$2f$lib$2f$recent$2d$chats$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["setRecentChatOwner"])(null);
        throw cause;
    }
}
async function getPublishedWork(id) {
    try {
        return await request(`/products/catalog/${encodeURIComponent(id)}`);
    } catch (cause) {
        if (cause instanceof ApiError && cause.status === 404) return request(`/products/${encodeURIComponent(id)}`);
        throw cause;
    }
}
function pageQuery(cursor) {
    const query = new URLSearchParams({
        limit: "30"
    });
    if (cursor) {
        query.set("cursor_created_at", cursor.createdAt);
        query.set("cursor_id", cursor.id);
    }
    return query.toString();
}
const listCatalog = (cursor, search = "", tagId = "")=>request(`/products/catalog?${pageQuery(cursor)}&search=${encodeURIComponent(search)}${tagId ? `&tag_id=${encodeURIComponent(tagId)}` : ""}`);
const listCatalogTags = ()=>request("/products/catalog-tags");
const listOwnedConversations = (cursor)=>request(`/conversations/mine?${pageQuery(cursor)}`);
const getCreditBalance = ()=>request("/account/credits");
const startConversation = (productId, startSetId)=>request("/conversations", {
        method: "POST",
        body: JSON.stringify({
            product_id: productId,
            start_set_id: startSetId
        })
    });
const getConversationStart = (id)=>request(`/conversations/${encodeURIComponent(id)}/start`);
const listMessages = (id, cursor)=>request(`/conversations/${encodeURIComponent(id)}/messages?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`);
async function listConversationMessages(id) {
    const messages = new Map();
    const seen = new Set();
    let cursor;
    do {
        const page = await listMessages(id, cursor);
        for (const message of page.items)messages.set(message.id, message);
        cursor = page.next_cursor ?? undefined;
        if (cursor && seen.has(cursor)) throw new Error("Message cursor did not advance.");
        if (cursor) seen.add(cursor);
    }while (cursor)
    return [
        ...messages.values()
    ].sort((a, b)=>a.position - b.position);
}
const createMessage = (id, content, requestKey)=>request(`/conversations/${encodeURIComponent(id)}/messages`, {
        method: "POST",
        body: JSON.stringify({
            request_key: requestKey,
            content
        })
    });
const generateAnswer = (id, message, productCharacterId, requestKey, signal, manualEntryIds = [])=>request(`/conversations/${encodeURIComponent(id)}/answers`, {
        method: "POST",
        signal,
        body: JSON.stringify({
            request_key: requestKey,
            input_message_id: message.id,
            expected_revision: message.revision,
            product_character_id: productCharacterId,
            manual_entry_ids: manualEntryIds
        })
    });
async function login(email, password) {
    const user = await request("/auth/login", {
        method: "POST",
        body: JSON.stringify({
            email,
            password
        })
    });
    localStorage.removeItem(REFRESH_UNCERTAIN_KEY);
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$apps$2f$web$2f$lib$2f$recent$2d$chats$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["setRecentChatOwner"])(user.id);
    localStorage.setItem(__TURBOPACK__imported__module__$5b$project$5d2f$apps$2f$web$2f$lib$2f$recent$2d$chats$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["AUTH_CHANGED_KEY"], crypto.randomUUID());
    window.dispatchEvent(new Event(__TURBOPACK__imported__module__$5b$project$5d2f$apps$2f$web$2f$lib$2f$recent$2d$chats$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["AUTH_CHANGED_KEY"]));
    return user;
}
async function getMe() {
    const user = await request("/auth/me");
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$apps$2f$web$2f$lib$2f$recent$2d$chats$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["setRecentChatOwner"])(user.id);
    return user;
}
const register = (email, password)=>request("/auth/register", {
        method: "POST",
        body: JSON.stringify({
            email,
            password
        })
    });
const resendVerification = (email)=>request("/auth/email/resend", {
        method: "POST",
        body: JSON.stringify({
            email
        })
    });
const verifyEmail = (token)=>request("/auth/email/verify", {
        method: "POST",
        body: JSON.stringify({
            token
        })
    });
const requestPasswordReset = (email)=>request("/auth/password/reset/request", {
        method: "POST",
        body: JSON.stringify({
            email
        })
    });
const resetPassword = (token, password)=>request("/auth/password/reset", {
        method: "POST",
        body: JSON.stringify({
            token,
            password
        })
    });
async function logout() {
    await request("/auth/logout", {
        method: "POST"
    });
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$apps$2f$web$2f$lib$2f$recent$2d$chats$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["setRecentChatOwner"])(null);
    localStorage.setItem(__TURBOPACK__imported__module__$5b$project$5d2f$apps$2f$web$2f$lib$2f$recent$2d$chats$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["AUTH_CHANGED_KEY"], crypto.randomUUID());
    window.dispatchEvent(new Event(__TURBOPACK__imported__module__$5b$project$5d2f$apps$2f$web$2f$lib$2f$recent$2d$chats$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["AUTH_CHANGED_KEY"]));
}
}),
"[project]/apps/web/lib/recent-chats.ts [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "AUTH_CHANGED_KEY",
    ()=>AUTH_CHANGED_KEY,
    "RECENT_CHATS_EVENT",
    ()=>RECENT_CHATS_EVENT,
    "RECENT_CHATS_KEY",
    ()=>RECENT_CHATS_KEY,
    "readRecentChats",
    ()=>readRecentChats,
    "setRecentChatOwner",
    ()=>setRecentChatOwner,
    "updateRecentChatMessage",
    ()=>updateRecentChatMessage,
    "upsertRecentChat",
    ()=>upsertRecentChat
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$apps$2f$web$2f$lib$2f$works$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/apps/web/lib/works.ts [app-ssr] (ecmascript)");
;
const RECENT_CHATS_KEY = "moseori_recent_chats";
const RECENT_CHATS_EVENT = "moseori:recent-chats-updated";
const AUTH_CHANGED_KEY = "moseori_auth_changed";
let currentOwner = null;
function setRecentChatOwner(owner) {
    if (currentOwner === owner) return;
    currentOwner = owner;
    if ("TURBOPACK compile-time falsy", 0) //TURBOPACK unreachable
    ;
}
function storageKey(owner) {
    return `${RECENT_CHATS_KEY}:v2:${owner ? `user:${owner}` : "demo"}`;
}
function readStoredChats(key) {
    if ("TURBOPACK compile-time truthy", 1) return [];
    //TURBOPACK unreachable
    ;
}
function readRecentChats(owner = currentOwner) {
    // Only demo rows have a known scope in the old shared cache. Never assign
    // legacy real conversations to whichever account happens to log in next.
    const demos = readStoredChats(storageKey(null));
    const legacyDemos = readStoredChats(RECENT_CHATS_KEY).filter((item)=>(0, __TURBOPACK__imported__module__$5b$project$5d2f$apps$2f$web$2f$lib$2f$works$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["isDemoWork"])(item.id));
    const owned = owner ? readStoredChats(storageKey(owner)) : [];
    const rows = new Map();
    for (const item of [
        ...legacyDemos,
        ...demos,
        ...owned
    ])rows.set(item.id, item);
    return [
        ...rows.values()
    ].sort((a, b)=>(b.updatedAt ?? 0) - (a.updatedAt ?? 0)).slice(0, 20);
}
function upsertRecentChat(next, owner = currentOwner) {
    const demo = (0, __TURBOPACK__imported__module__$5b$project$5d2f$apps$2f$web$2f$lib$2f$works$2e$ts__$5b$app$2d$ssr$5d$__$28$ecmascript$29$__["isDemoWork"])(next.id);
    if (!demo && !owner) return;
    const key = storageKey(demo ? null : owner);
    const saved = readStoredChats(key);
    const previous = saved.find((item)=>item.id === next.id);
    const merged = {
        ...previous,
        ...next,
        updatedAt: Date.now()
    };
    localStorage.setItem(key, JSON.stringify([
        merged,
        ...saved.filter((item)=>item.id !== next.id)
    ].slice(0, 20)));
    window.dispatchEvent(new Event(RECENT_CHATS_EVENT));
}
function updateRecentChatMessage(id, lastMessage, owner = currentOwner) {
    const previous = readRecentChats(owner).find((item)=>item.id === id);
    if (previous) upsertRecentChat({
        ...previous,
        lastMessage
    }, owner);
}
}),
"[project]/apps/web/lib/works.ts [app-ssr] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "demoWorkById",
    ()=>demoWorkById,
    "demoWorks",
    ()=>demoWorks,
    "isDemoWork",
    ()=>isDemoWork
]);
const demoWorks = [
    {
        id: "demo-archive",
        coverImage: "/images/stories/archive.png",
        title: "밤의 기록 보관소",
        subtitle: "사라진 기억을 보관하는 도서관에서 당신 앞으로 온 편지 한 통.",
        genre: "미스터리",
        tags: [
            "도서관",
            "비밀",
            "판타지"
        ],
        author: "별의서재",
        color: "#151b31",
        accent: "#c3a77b",
        symbol: "✧",
        popularity: "2.4k",
        badge: "EDITOR'S PICK",
        opening: "자정이 넘자 보관소의 시계가 열세 번 울렸다. 책장 사이에서 누군가 당신의 이름을 불렀다. 돌아보니 낯선 편지가 바닥에 놓여 있었다.",
        startOptions: [
            {
                id: "letter",
                title: "편지를 열어본다",
                preview: "봉투에는 오래전 잊은 필체로 당신의 이름이 적혀 있다."
            },
            {
                id: "voice",
                title: "목소리를 따라간다",
                preview: "꺼진 등 뒤로 희미한 발소리가 이어진다."
            }
        ]
    },
    {
        id: "demo-bluehour",
        coverImage: "/images/stories/bluehour.png",
        title: "푸른 시간의 역",
        subtitle: "막차가 떠난 플랫폼에서 다시 만난 오래된 친구.",
        genre: "로맨스",
        tags: [
            "재회",
            "현대",
            "감성"
        ],
        author: "유월",
        color: "#315478",
        accent: "#d7c6b0",
        symbol: "☾",
        popularity: "1.8k",
        opening: "마지막 열차가 떠난 뒤에도 플랫폼에는 네가 남아 있었다. 바람에 흩날린 머리카락을 넘기며 네가 웃는다. ‘정말 올 줄은 몰랐어.’",
        startOptions: [
            {
                id: "platform",
                title: "플랫폼에서",
                preview: "서로 할 말이 많지만, 첫마디는 쉽지 않다."
            }
        ]
    },
    {
        id: "demo-garden",
        coverImage: "/images/stories/garden.png",
        title: "유리 온실의 계약",
        subtitle: "꽃이 사람의 비밀을 기억한다는 도시의 작은 온실.",
        genre: "판타지",
        tags: [
            "마법",
            "힐링",
            "계약"
        ],
        author: "온실지기",
        color: "#275047",
        accent: "#e0b9a0",
        symbol: "❋",
        popularity: "980",
        badge: "NEW",
        opening: "비를 피해 들어온 온실은 이상할 만큼 따뜻했다. 주인이 빈 화분 하나를 내밀며 말했다. ‘여기에 묻고 싶은 이야기가 있으신가요?’",
        startOptions: [
            {
                id: "rain",
                title: "비 오는 오후",
                preview: "유리 지붕을 두드리는 빗소리만 들린다."
            }
        ]
    },
    {
        id: "demo-radio",
        coverImage: "/images/stories/radio.png",
        title: "새벽 2시 라디오",
        subtitle: "전파가 닿지 않는 곳에서 들려온 당신만의 방송.",
        genre: "일상",
        tags: [
            "라디오",
            "새벽",
            "대화"
        ],
        author: "모노",
        color: "#6a3c47",
        accent: "#f1bd83",
        symbol: "◉",
        popularity: "3.1k",
        opening: "잡음 사이로 목소리가 흘러나왔다. ‘여기는 새벽 두 시, 당신에게만 들리는 방송입니다. 오늘은 어떤 하루였나요?’",
        startOptions: [
            {
                id: "signal",
                title: "주파수를 맞춘다",
                preview: "작은 다이얼을 돌리자 음악이 멈춘다."
            }
        ]
    },
    {
        id: "demo-orbit",
        title: "우주의 끝에서",
        subtitle: "조난 신호를 보낸 우주선에는 한 사람만 남아 있었다.",
        genre: "SF",
        tags: [
            "우주",
            "탐사",
            "선택"
        ],
        author: "궤도",
        color: "#263a57",
        accent: "#a7c4d5",
        symbol: "✦",
        popularity: "1.2k",
        opening: "통신이 연결되자 화면에는 고장 난 조종석이 보였다. 상대가 카메라를 올려다본다. ‘아직 누군가 듣고 있었군요.’",
        startOptions: [
            {
                id: "signal",
                title: "구조 신호",
                preview: "수신 좌표는 지도에 표시되지 않는 구역을 가리킨다."
            }
        ]
    },
    {
        id: "demo-cafe",
        title: "계절을 파는 카페",
        subtitle: "다시 만나고 싶은 날의 날씨를 주문할 수 있다면.",
        genre: "힐링",
        tags: [
            "카페",
            "마법",
            "일상"
        ],
        author: "서쪽창가",
        color: "#845e45",
        accent: "#efd0a4",
        symbol: "✿",
        popularity: "760",
        opening: "작은 종이 울리며 문이 열렸다. 메뉴판에는 커피 대신 계절이 적혀 있었다. ‘오늘은 어떤 날을 다시 만나고 싶으세요?’",
        startOptions: [
            {
                id: "menu",
                title: "메뉴판 앞에서",
                preview: "봄, 여름, 가을, 겨울. 단 하나만 고를 수 있다."
            }
        ]
    }
];
const demoWorkById = (id)=>demoWorks.find((work)=>work.id === id);
function isDemoWork(id) {
    return id.startsWith("demo-");
}
}),
];

//# sourceMappingURL=apps_web_1dfepr7._.js.map
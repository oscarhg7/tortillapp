(function () {
    'use strict';

    var STORAGE_KEY = 'tortillapp_cookie_consent';

    // Si ya decidió, no mostrar nada
    if (localStorage.getItem(STORAGE_KEY)) return;

    /* ── Estilos ─────────────────────────────────────────────── */
    var css = `
        #cookie-banner {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            z-index: 9999;
            background: #0f172a;
            border-top: 2px solid #FFD700;
            padding: 16px 20px;
            box-shadow: 0 -4px 24px rgba(0,0,0,0.5);
            font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
            font-size: 0.88rem;
            color: #cbd5e1;
            animation: cookieSlideUp 0.35s ease;
        }
        @keyframes cookieSlideUp {
            from { transform: translateY(100%); opacity: 0; }
            to   { transform: translateY(0);    opacity: 1; }
        }
        #cookie-banner .cookie-inner {
            max-width: 860px;
            margin: 0 auto;
            display: flex;
            align-items: center;
            gap: 16px;
            flex-wrap: wrap;
        }
        #cookie-banner .cookie-text {
            flex: 1;
            min-width: 220px;
            line-height: 1.5;
        }
        #cookie-banner .cookie-text strong {
            color: #f8fafc;
        }
        #cookie-banner .cookie-text a {
            color: #FFD700;
            text-decoration: underline;
            cursor: pointer;
        }
        #cookie-banner .cookie-btns {
            display: flex;
            gap: 10px;
            flex-shrink: 0;
        }
        #cookie-banner .btn-accept-all {
            background: #FFD700;
            color: #0f172a;
            border: none;
            padding: 9px 18px;
            border-radius: 8px;
            font-weight: 700;
            font-size: 0.88rem;
            cursor: pointer;
            transition: background 0.2s;
            white-space: nowrap;
        }
        #cookie-banner .btn-accept-all:hover { background: #fac430; }
        #cookie-banner .btn-reject {
            background: transparent;
            color: #94a3b8;
            border: 1px solid #475569;
            padding: 9px 18px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 0.88rem;
            cursor: pointer;
            transition: border-color 0.2s, color 0.2s;
            white-space: nowrap;
        }
        #cookie-banner .btn-reject:hover { border-color: #94a3b8; color: #f8fafc; }

        /* Modal política de cookies */
        #cookie-modal-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.75);
            z-index: 10000;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
        }
        #cookie-modal {
            background: #1e293b;
            border: 1px solid #475569;
            border-radius: 16px;
            width: 100%;
            max-width: 520px;
            max-height: 80vh;
            display: flex;
            flex-direction: column;
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
        }
        #cookie-modal .cm-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 18px 22px 14px;
            border-bottom: 1px solid #334155;
        }
        #cookie-modal .cm-header h2 {
            color: #FFD700;
            font-size: 1rem;
            font-weight: 700;
            margin: 0;
        }
        #cookie-modal .cm-close {
            background: none;
            border: none;
            color: #94a3b8;
            font-size: 1.5rem;
            cursor: pointer;
            line-height: 1;
            padding: 0 4px;
        }
        #cookie-modal .cm-close:hover { color: #FFD700; }
        #cookie-modal .cm-body {
            padding: 18px 22px;
            overflow-y: auto;
            flex: 1;
            color: #cbd5e1;
            font-size: 0.88rem;
            line-height: 1.65;
        }
        #cookie-modal .cm-body h3 {
            color: #f8fafc;
            font-size: 0.9rem;
            font-weight: 700;
            margin: 16px 0 6px;
        }
        #cookie-modal .cm-body h3:first-child { margin-top: 0; }
        #cookie-modal .cm-body p { margin: 0 0 8px; }
        #cookie-modal .cm-body table {
            width: 100%;
            border-collapse: collapse;
            margin: 8px 0 12px;
            font-size: 0.82rem;
        }
        #cookie-modal .cm-body th {
            background: #0f172a;
            color: #94a3b8;
            padding: 6px 10px;
            text-align: left;
            font-weight: 600;
        }
        #cookie-modal .cm-body td {
            padding: 6px 10px;
            border-bottom: 1px solid #1e293b;
            color: #cbd5e1;
            vertical-align: top;
        }
        #cookie-modal .cm-body tr:nth-child(even) td { background: #0f172a33; }
        #cookie-modal .cm-footer {
            padding: 14px 22px 18px;
            border-top: 1px solid #334155;
            display: flex;
            gap: 10px;
        }
        #cookie-modal .cm-footer button {
            flex: 1;
            padding: 10px;
            border-radius: 8px;
            font-weight: 700;
            font-size: 0.88rem;
            cursor: pointer;
            border: none;
        }
        #cookie-modal .cm-btn-accept {
            background: #FFD700;
            color: #0f172a;
        }
        #cookie-modal .cm-btn-accept:hover { background: #fac430; }
        #cookie-modal .cm-btn-reject {
            background: transparent;
            color: #94a3b8;
            border: 1px solid #475569 !important;
        }
        #cookie-modal .cm-btn-reject:hover { color: #f8fafc; border-color: #94a3b8 !important; }
    `;

    var styleTag = document.createElement('style');
    styleTag.textContent = css;
    document.head.appendChild(styleTag);

    /* ── Banner ──────────────────────────────────────────────── */
    var banner = document.createElement('div');
    banner.id = 'cookie-banner';
    banner.innerHTML = `
        <div class="cookie-inner">
            <div class="cookie-text">
                <strong>Usamos cookies</strong> — propias (sesión, necesarias) y de terceros con fines publicitarios.
                Puedes aceptarlas todas o solo las estrictamente necesarias.
                <a onclick="window.__showCookiePolicy()">Política de cookies</a>
            </div>
            <div class="cookie-btns">
                <button class="btn-reject"     onclick="window.__setCookies('essential')">Solo necesarias</button>
                <button class="btn-accept-all" onclick="window.__setCookies('all')">Aceptar todas</button>
            </div>
        </div>
    `;
    document.body.appendChild(banner);

    /* ── Funciones globales ───────────────────────────────────── */
    window.__setCookies = function (level) {
        localStorage.setItem(STORAGE_KEY, level);
        document.getElementById('cookie-banner').remove();
        var modal = document.getElementById('cookie-modal-overlay');
        if (modal) modal.remove();
        if (level === 'all') window.__loadAds && window.__loadAds();
    };

    window.__showCookiePolicy = function () {
        if (document.getElementById('cookie-modal-overlay')) return;
        var overlay = document.createElement('div');
        overlay.id = 'cookie-modal-overlay';
        overlay.onclick = function (e) { if (e.target === overlay) overlay.remove(); };
        overlay.innerHTML = `
            <div id="cookie-modal">
                <div class="cm-header">
                    <h2>Política de Cookies</h2>
                    <button class="cm-close" onclick="document.getElementById('cookie-modal-overlay').remove()">&times;</button>
                </div>
                <div class="cm-body">
                    <p>Esta web utiliza cookies propias y de terceros. A continuación te explicamos qué cookies usamos y para qué.</p>

                    <h3>¿Qué es una cookie?</h3>
                    <p>Una cookie es un pequeño fichero de texto que se almacena en tu dispositivo cuando visitas una web. Sirve para recordar información sobre tu visita y mejorar tu experiencia.</p>

                    <h3>Cookies que utilizamos</h3>
                    <table>
                        <thead><tr><th>Nombre</th><th>Tipo</th><th>Finalidad</th><th>Duración</th></tr></thead>
                        <tbody>
                            <tr><td>session</td><td>Propia · Necesaria</td><td>Mantiene tu sesión iniciada</td><td>Sesión</td></tr>
                            <tr><td>tortillapp_cookie_consent</td><td>Propia · Necesaria</td><td>Guarda tu elección sobre cookies</td><td>1 año</td></tr>
                            <tr><td>Cookies de Google AdSense</td><td>Terceros · Publicitaria</td><td>Mostrar anuncios personalizados según tus intereses</td><td>Hasta 2 años</td></tr>
                        </tbody>
                    </table>

                    <h3>Base legal (RGPD y LSSI)</h3>
                    <p>Las cookies necesarias se instalan en base al <strong>interés legítimo</strong> del titular del sitio. Las cookies publicitarias requieren tu <strong>consentimiento expreso</strong>, que puedes retirar en cualquier momento borrando los datos de tu navegador.</p>

                    <h3>¿Cómo desactivarlas?</h3>
                    <p>Puedes rechazar las cookies no esenciales en el banner que aparece al entrar, o configurar tu navegador para bloquearlas. Ten en cuenta que bloquear las cookies necesarias puede impedir el correcto funcionamiento de la aplicación.</p>

                    <h3>Más información</h3>
                    <p>Para cualquier consulta sobre el tratamiento de tus datos, puedes contactar con nosotros a través del email de registro.</p>
                </div>
                <div class="cm-footer">
                    <button class="cm-btn-reject" onclick="window.__setCookies('essential')">Solo necesarias</button>
                    <button class="cm-btn-accept" onclick="window.__setCookies('all')">Aceptar todas</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
    };

    /* ── Cargar anuncios si ya consintió en sesión anterior ─── */
    if (localStorage.getItem(STORAGE_KEY) === 'all') {
        window.__loadAds && window.__loadAds();
    }
})();

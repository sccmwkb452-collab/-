import Script from "next/script";

export function AnalyticsScripts() {
  const ymId = process.env.NEXT_PUBLIC_YANDEX_METRIKA_ID;
  const gaId = process.env.NEXT_PUBLIC_GA_ID;
  const safeYm = ymId && /^\d+$/.test(ymId) ? ymId : null;
  const safeGa = gaId && /^[A-Z0-9-]+$/.test(gaId) ? gaId : null;

  return (
    <>
      {safeYm && (
        <Script id="ym" strategy="afterInteractive">
          {`(function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};m[i].l=1*new Date();k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})(window,document,"script","https://mc.yandex.ru/metrika/tag.js","ym");ym(${safeYm},"init",{clickmap:true,trackLinks:true,accurateTrackBounce:true,webvisor:true});`}
        </Script>
      )}
      {safeGa && (
        <>
          <Script src={`https://www.googletagmanager.com/gtag/js?id=${safeGa}`} strategy="afterInteractive" />
          <Script id="ga" strategy="afterInteractive">
            {`window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}window.gtag=gtag;gtag('js',new Date());gtag('config','${safeGa}');`}
          </Script>
        </>
      )}
    </>
  );
}

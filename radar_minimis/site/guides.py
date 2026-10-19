"""Guías evergreen para asesorías: una por búsqueda de alta intención, todas enlazadas a la calculadora.

Contenido redactado a mano y contrastado con los reglamentos citados (ver research/raw/07_verificacion_normativa.md).
El HTML es de confianza (lo escribe el proyecto, no viene de la BDNS) y se inserta sin escapar.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Guide:
    slug: str
    title: str
    h1: str
    description: str
    lede: str
    body: str
    faq: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def path(self) -> str:
        return f"/guias/{self.slug}/"


GUIDES: tuple[Guide, ...] = (
    Guide(
        slug="que-es-una-ayuda-de-minimis",
        title="Qué es una ayuda de minimis y cuánto se puede recibir (2026)",
        h1="Qué es una ayuda de minimis y cuánto puede recibir una empresa",
        description="Definición de ayuda de minimis, tope de 300.000 € en tres años (Reg. (UE) 2023/2831), "
        "a quién se aplica y cómo comprobar el margen disponible de una empresa por CIF.",
        lede="Las ayudas de minimis son ayudas públicas de importe reducido que la Unión Europea considera "
        "incapaces de falsear la competencia. Por eso no se notifican a la Comisión, pero tienen un tope por empresa.",
        body="""
<h2>Definición</h2>
<p>Una ayuda de minimis es una ayuda de Estado de pequeña cuantía que queda fuera del control previo de la Comisión
Europea porque no supera un tope por empresa en un período de tres años. El régimen general está en el
<strong>Reglamento (UE) 2023/2831</strong>, aplicable desde el 1 de enero de 2024 hasta el 31 de diciembre de 2030.</p>
<p>La mayoría de convocatorias de pequeñas subvenciones a empresas (digitalización, contratación, ferias,
eficiencia energética, comercio local) se acogen a este régimen. Las bases lo indican expresamente y suelen exigir una
declaración responsable sobre las ayudas de minimis recibidas.</p>
<h2>Cuánto se puede recibir</h2>
<table class="kv">
<tr><th>Régimen general</th><td><span class="mono">300.000 €</span> por «única empresa» en tres años
(Reg. (UE) 2023/2831, art. 3.2). Antes de 2024 el tope era de 200.000 €.</td></tr>
<tr><th>SIEG</th><td><span class="mono">750.000 €</span> en tres años para servicios de interés económico general
(Reg. (UE) 2023/2832).</td></tr>
<tr><th>Producción agrícola primaria</th><td><span class="mono">50.000 €</span> en tres años
(Reg. (UE) 1408/2013, en la redacción del Reg. (UE) 2024/3118).</td></tr>
<tr><th>Pesca y acuicultura</th><td><span class="mono">30.000 €</span> en el ejercicio en curso y los dos anteriores;
<span class="mono">40.000 €</span> en España, que dispone de registro central (Reg. (UE) 717/2014, art. 3.2 bis,
y RD 1139/2024).</td></tr>
</table>
<p>El tope es por <a href="/guias/unica-empresa-minimis/">«única empresa»</a>: si la sociedad tiene matriz o filiales,
las ayudas de todo el grupo se suman.</p>
<h2>Qué cuenta y qué no</h2>
<ul>
<li>Cuenta el <strong>equivalente de subvención bruta</strong>: para una subvención, su importe; para un préstamo o
una garantía, el valor de la ventaja que suponen.</li>
<li>La ayuda computa en la <strong>fecha de concesión</strong> (cuando nace el derecho a recibirla), no en la de pago
(art. 3.3).</li>
<li>Se suman todas las ayudas de minimis, las conceda quien las conceda: Estado, comunidad autónoma, diputación o
ayuntamiento.</li>
</ul>
<h2>Cómo saber cuánto margen le queda a una empresa</h2>
<p>En España las concesiones de minimis se registran en la Base de Datos Nacional de Subvenciones (BDNS), que hace de
registro central en el sentido del art. 6 del Reglamento (UE) 2023/2831. La <a href="/minimis/">calculadora por CIF</a> suma las concesiones registradas en los tres años
anteriores a la fecha que indiques y muestra el margen de cada régimen.</p>
""",
        faq=(
            (
                "¿Las ayudas de minimis se notifican a Bruselas?",
                "No. Precisamente por no superar el tope quedan exentas de notificación previa a la Comisión Europea.",
            ),
            (
                "¿Un autónomo puede recibir ayudas de minimis?",
                "Sí. El régimen se aplica a cualquier empresa, también a personas físicas que ejercen una actividad "
                "económica. La calculadora solo admite CIF de personas jurídicas por protección de datos.",
            ),
        ),
    ),
    Guide(
        slug="periodo-tres-anos-minimis",
        title="Cómo se cuentan los tres años de minimis: cómputo fecha a fecha",
        h1="Cómo se cuentan los tres años de las ayudas de minimis",
        description="El Reg. (UE) 2023/2831 sustituye los tres ejercicios fiscales por tres años móviles. Ejemplos "
        "de ventana, fecha de concesión y caso del 29 de febrero.",
        lede="Desde 2024 el período de tres años es móvil: se cuenta hacia atrás desde la fecha de cada nueva "
        "concesión, día a día, y ya no por ejercicios fiscales.",
        body="""
<h2>De ejercicios fiscales a años móviles</h2>
<p>El antiguo Reglamento (UE) 1407/2013 contaba el ejercicio fiscal en curso y los dos anteriores. El
<strong>Reglamento (UE) 2023/2831</strong> cambia el criterio: el tope se aplica sobre «cualquier período de tres
años» (art. 3.2), que el considerando 11 describe como un cómputo continuo. Cada vez que se concede una ayuda nueva
hay que sumar todo lo concedido en los tres años anteriores a esa fecha.</p>
<h2>Ejemplo de ventana</h2>
<table class="kv">
<tr><th>Fecha prevista de concesión</th><td class="mono">19/10/2026</td></tr>
<tr><th>Ventana computada</th><td><span class="mono">20/10/2023</span> a <span class="mono">19/10/2026</span>, ambos
incluidos</td></tr>
<tr><th>Fuera de la ventana</th><td>Una ayuda concedida el <span class="mono">19/10/2023</span> ya no computa</td></tr>
</table>
<p>Si la fecha de referencia es un 29 de febrero, la ventana arranca el día siguiente al 28 de febrero de tres años
antes.</p>
<h2>Qué fecha cuenta</h2>
<p>La de <strong>concesión</strong>: el momento en que la empresa adquiere el derecho legal a recibir la ayuda conforme
al régimen nacional aplicable (art. 3.3), con independencia de cuándo se pague. Por eso conviene calcular el margen
con la fecha prevista de resolución de la nueva ayuda, no con la de la solicitud.</p>
<h2>Excepción: pesca</h2>
<p>El reglamento de pesca (Reg. (UE) 717/2014) mantiene el cómputo por ejercicios: el ejercicio en curso y los dos
anteriores.</p>
<p>La <a href="/minimis/">calculadora</a> permite indicar la fecha prevista de concesión y aplica cada criterio a su
régimen.</p>
""",
        faq=(
            (
                "¿Las ayudas del Reglamento 1407/2013 siguen contando?",
                "Sí, si se concedieron dentro de los tres años anteriores a la nueva concesión. El cambio de reglamento "
                "no reinicia el contador.",
            ),
            (
                "¿Cuándo deja de contar una ayuda?",
                "Al día siguiente de cumplirse tres años desde su fecha de concesión.",
            ),
        ),
    ),
    Guide(
        slug="declaracion-responsable-minimis",
        title="Modelo de declaración responsable de ayudas de minimis",
        h1="Declaración responsable de ayudas de minimis: modelo y contenido",
        description="Qué debe incluir la declaración responsable de minimis que piden las convocatorias, modelo "
        "orientativo y cómo preparar la relación de ayudas de los tres últimos años.",
        lede="Casi todas las convocatorias acogidas al régimen de minimis piden al solicitante que declare las "
        "ayudas de minimis recibidas en los tres años anteriores. Un error puede suponer el reintegro de la ayuda.",
        body="""
<h2>Qué debe contener</h2>
<ul>
<li>Identificación del firmante y de la empresa solicitante (razón social y CIF).</li>
<li>Relación de las ayudas de minimis recibidas en los <a href="/guias/periodo-tres-anos-minimis/">tres años
anteriores</a> a la fecha de concesión: órgano concedente, fecha de concesión, importe y reglamento.</li>
<li>Las ayudas de las empresas con las que forma una <a href="/guias/unica-empresa-minimis/">«única empresa»</a>.</li>
<li>La declaración expresa de que no ha recibido otras ayudas de minimis distintas de las relacionadas.</li>
<li>El compromiso de comunicar cualquier ayuda nueva que se conceda antes de resolver.</li>
</ul>
<p>Cada convocatoria puede exigir su propio modelo: usa siempre el anexo de las bases si existe.</p>
<h2>Modelo orientativo</h2>
<div class="notice">
<p>D./D.ª ______________________, con DNI/NIE __________, en representación de ______________________, con CIF
__________, DECLARA bajo su responsabilidad:</p>
<p>1. Que la empresa, junto con las empresas con las que forma una «única empresa» en el sentido del art. 2.2 del
Reglamento (UE) 2023/2831, ha recibido en los tres años anteriores a la fecha de concesión las siguientes ayudas de
minimis: [órgano concedente, fecha de concesión, importe, reglamento].</p>
<p>2. Que no ha recibido otras ayudas de minimis distintas de las relacionadas.</p>
<p>3. Que se compromete a comunicar cualquier otra ayuda de minimis que se le conceda hasta la resolución.</p>
<p>En __________, a ___ de __________ de ____. Firma: __________</p>
</div>
<h2>Cómo preparar la relación de ayudas</h2>
<p>La parte laboriosa es reunir las concesiones. La <a href="/minimis/">calculadora</a> las obtiene de la BDNS por CIF
y genera un informe imprimible con la relación de concesiones, la hora de consulta, el margen por régimen y este
mismo borrador de declaración ya rellenado con los datos de la empresa.</p>
""",
        faq=(
            (
                "¿Qué pasa si la declaración omite una ayuda?",
                "Si con la ayuda omitida se superaba el tope, la nueva ayuda no puede acogerse al régimen de minimis y "
                "puede exigirse su reintegro con intereses.",
            ),
            (
                "¿Sirve el informe de la calculadora como certificado?",
                "No. Es un documento orientativo que facilita la declaración; la responsabilidad de lo declarado es "
                "del solicitante.",
            ),
        ),
    ),
    Guide(
        slug="unica-empresa-minimis",
        title="Única empresa en minimis: cuándo se suman las ayudas de empresas vinculadas",
        h1="«Única empresa» en minimis: cuándo se suman las ayudas del grupo",
        description="Los cuatro vínculos del art. 2.2 del Reg. (UE) 2023/2831 que obligan a sumar las ayudas de "
        "minimis de matriz y filiales, con ejemplos para asesorías.",
        lede="El tope de minimis no es por CIF sino por «única empresa»: un grupo de sociedades vinculadas comparte "
        "un único tope de 300.000 €.",
        body="""
<h2>Los cuatro vínculos</h2>
<p>Según el art. 2.2 del Reglamento (UE) 2023/2831, forman una «única empresa» todas las empresas entre las que exista
al menos uno de estos vínculos:</p>
<ol>
<li>Una posee la mayoría de los derechos de voto de los accionistas o socios de otra.</li>
<li>Una tiene derecho a nombrar o revocar a la mayoría de los miembros del órgano de administración, dirección o
control de otra.</li>
<li>Una tiene derecho a ejercer una influencia dominante sobre otra en virtud de un contrato o de sus estatutos.</li>
<li>Una, accionista o socia de otra, controla sola, por acuerdo con otros socios, la mayoría de los derechos de
voto.</li>
</ol>
<p>Los vínculos establecidos a través de otras empresas también cuentan.</p>
<h2>Ejemplo</h2>
<table class="kv">
<tr><th>Matriz</th><td>Holding Demo, SL: <span class="mono">120.000 €</span> de minimis en tres años</td></tr>
<tr><th>Filial al 60 %</th><td>Talleres Demo, SL: <span class="mono">150.000 €</span></td></tr>
<tr><th>Margen del grupo</th><td><span class="mono">30.000 €</span>, no 150.000 € como parecería mirando solo la
filial</td></tr>
</table>
<h2>Qué no crea una «única empresa»</h2>
<p>Las participaciones minoritarias sin control, compartir administrador sin control societario o tener los mismos
clientes no bastan por sí solos. Ante la duda, revisa la estructura de voto y los pactos de socios.</p>
<p>La <a href="/minimis/">calculadora</a> suma las concesiones del CIF principal y de sus vinculadas. Gratis hasta 2 CIF;
el <a href="/asesorias/">plan Asesorías Pro</a> admite grupos de 4.</p>
""",
    ),
    Guide(
        slug="consultar-ayudas-minimis-bdns",
        title="Cómo consultar las ayudas de minimis de una empresa en la BDNS",
        h1="Cómo consultar las ayudas de minimis de una empresa en la BDNS",
        description="Paso a paso para consultar las concesiones de minimis de un CIF en el portal de la BDNS "
        "(infosubvenciones.es) y cómo automatizar la suma de los tres años.",
        lede="La Base de Datos Nacional de Subvenciones publica las concesiones de minimis. Se pueden consultar por "
        "CIF en el portal del Sistema Nacional de Publicidad de Subvenciones.",
        body="""
<h2>En el portal oficial</h2>
<ol>
<li>Entra en <a href="https://www.infosubvenciones.es/" rel="nofollow noopener">infosubvenciones.es</a>, portal del
Sistema Nacional de Publicidad de Subvenciones, y abre la consulta de concesiones de minimis.</li>
<li>Indica el CIF del beneficiario y un rango de fechas de concesión que cubra los tres años anteriores a la nueva
ayuda.</li>
<li>Revisa cada fila: fecha de concesión, órgano concedente, reglamento y ayuda equivalente.</li>
<li>Suma los importes por régimen y réstalos de su tope. Repite con cada empresa vinculada.</li>
</ol>
<h2>Limitaciones</h2>
<ul>
<li>Las concesiones pueden tardar en registrarse: una ayuda recién concedida puede no aparecer todavía.</li>
<li>El buscador muestra coincidencias parciales del CIF: comprueba que cada fila es exactamente la empresa.</li>
<li>Los datos de personas físicas no pueden reutilizarse con fines comerciales.</li>
</ul>
<h2>Automatizado</h2>
<p>La <a href="/minimis/">calculadora por CIF</a> hace esta consulta contra la API pública de la BDNS, descarta las
coincidencias parciales, aplica la ventana de tres años fecha a fecha y separa los regímenes general, SIEG, agrícola y
pesca. Para una cartera de clientes, el <a href="/asesorias/">panel de asesorías</a> revisa hasta 100 CIF de una vez
y marca las concesiones nuevas desde la revisión anterior.</p>
""",
    ),
    Guide(
        slug="topes-minimis-por-sector",
        title="Topes de minimis por sector: general, SIEG, agrícola y pesca (2026)",
        h1="Topes de minimis por sector en 2026",
        description="300.000 € general, 750.000 € SIEG, 50.000 € agrícola y 40.000 € pesca en España: reglamento, "
        "período de cómputo y cómo se acumulan entre sí.",
        lede="Cada régimen de minimis tiene su propio tope y su propio reglamento. Una empresa con varias "
        "actividades puede estar sujeta a más de uno.",
        body="""
<table class="kv">
<tr><th>General · Reg. (UE) 2023/2831</th><td><span class="mono">300.000 €</span> · tres años móviles</td></tr>
<tr><th>SIEG · Reg. (UE) 2023/2832</th><td><span class="mono">750.000 €</span> · tres años móviles</td></tr>
<tr><th>Agrícola · Reg. (UE) 1408/2013</th><td><span class="mono">50.000 €</span> · tres años móviles (redacción del
Reg. (UE) 2024/3118)</td></tr>
<tr><th>Pesca · Reg. (UE) 717/2014</th><td><span class="mono">40.000 €</span> en España (<span class="mono">30.000 €
</span> régimen base) · ejercicio en curso y dos anteriores</td></tr>
</table>
<h2>Acumulación entre regímenes</h2>
<ul>
<li>Las ayudas agrícolas y de pesca pueden acumularse con las generales, pero el total no puede superar el tope
general de 300.000 € (art. 5.2 del Reg. (UE) 2023/2831).</li>
<li>Las ayudas SIEG pueden acumularse con las generales (art. 5.1). El reglamento no fija un tope conjunto expreso; la
calculadora aplica el criterio prudente de no superar 750.000 € entre ambas.</li>
</ul>
<h2>Transporte de mercancías por carretera</h2>
<p>El Reglamento (UE) 1407/2013 fijaba un tope reducido de 100.000 € para el transporte de mercancías por carretera
por cuenta ajena. El Reglamento (UE) 2023/2831 lo suprime: desde 2024 se aplica el tope general.</p>
<p>La <a href="/minimis/">calculadora</a> clasifica cada concesión por su reglamento y aplica estos topes y criterios de
acumulación.</p>
""",
    ),
    Guide(
        slug="superar-tope-minimis",
        title="Qué pasa si se supera el tope de minimis",
        h1="Qué ocurre si una empresa supera el tope de minimis",
        description="Consecuencias de superar el tope de minimis: la nueva ayuda no puede acogerse al reglamento, "
        "posible reintegro con intereses y alternativas.",
        lede="El tope de minimis no se puede rebasar ni en parte: si una nueva ayuda lo supera, esa ayuda entera queda "
        "fuera del régimen.",
        body="""
<h2>La regla</h2>
<p>Si con la concesión de una nueva ayuda se superase el tope aplicable, esa nueva ayuda no puede acogerse al
Reglamento (UE) 2023/2831, <strong>ni siquiera por la parte que no excede del tope</strong> (art. 3). No cabe
fraccionarla para quedarse en el límite.</p>
<h2>Consecuencias</h2>
<ul>
<li>La administración no puede concederla como minimis. Si ya la concedió por un error en la declaración, la ayuda es
una ayuda de Estado no notificada.</li>
<li>Procede su reintegro con intereses de demora conforme a la Ley 38/2003, General de Subvenciones, además de las
posibles sanciones por falsedad en la declaración responsable.</li>
</ul>
<h2>Alternativas</h2>
<ul>
<li>Esperar a que salgan de la ventana de tres años las ayudas más antiguas: la calculadora permite probar fechas
futuras de concesión.</li>
<li>Buscar convocatorias acogidas a otro régimen, como el Reglamento general de exención por categorías, que no
computa contra el tope de minimis.</li>
</ul>
<p>Comprueba el margen antes de solicitar con la <a href="/minimis/">calculadora por CIF</a>.</p>
""",
        faq=(
            (
                "¿Se puede reducir la ayuda solicitada para no superar el tope?",
                "Sí, si las bases lo permiten y se solicita un importe que quepa en el margen. Lo que no se admite es "
                "conceder una ayuda que supere el tope y acoger solo una parte al régimen de minimis.",
            ),
        ),
    ),
)

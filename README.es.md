# Verdadero pero invisible: Grok como fact-checker en X

**¿Acierta un verificador basado en IA? ¿Y su corrección llega a alguien?**

Construí un corpus de 2.353 interacciones reales en las que usuarios de X pedían a Grok verificar una publicación (*"@grok is this true?"*). Comparé cada veredicto con el de un modelo independiente (Gemini) y medí qué parte de la audiencia original alcanzaba cada corrección.

[English version](README.md) · [Paper (5 páginas)](paper/true_but_invisible_paper_ES.pdf) · TFM del Máster en Data Analytics for Business, UPF Barcelona School of Management (2026)

## Resultados principales

- **Concordancia:** Grok y Gemini llegan al mismo veredicto, o casi, en el **82%** de los casos.
- **Desacuerdo:** controlando el resto de variables, se concentra en **guerra** y **política**. El idioma y el periodo tienen efectos significativos pero pequeños.
- **Alcance:** el fact-check típico de Grok llega solo al **0,3%** de la audiencia del tweet que corrige. Solo 1 de cada 10 supera en visualizaciones al original.

**Conclusión:** el cuello de botella de la verificación automatizada no es la calidad del juicio, sino su difusión.

## Cómo se hizo

1. **Recogida:** scraping con Apify de respuestas de Grok con vocabulario de verificación (43 términos en inglés y español, dos periodos: 2025 y 2026). Después, reconstrucción de cada hilo de tres tweets (afirmación → petición → respuesta) mediante `inReplyToId`.
2. **Limpieza:** de 8.055 respuestas a 2.353 interacciones analizables.
3. **Anotación con LLMs:** Gemini 3.1 Flash Lite (con Google Search) genera un fact-check de referencia. Un modelo distinto, Gemini 3.5 Flash, actúa como juez de la concordancia, da su confianza y asigna la temática.
4. **Análisis:** Kruskal-Wallis con tamaño de efecto y corrección de Holm, post-hoc de Dunn, regresión logística ordinal, Cochran-Mantel-Haenszel y ratio de captura de audiencia.

Toda la metodología, las figuras y la estructura del repositorio están en el [README en inglés](README.md). El notebook [`02_analysis.ipynb`](notebooks/02_analysis.ipynb) reproduce todas las cifras sin necesidad de claves de API.

## Equipo

TFM en grupo: Diego Gamarra, Antoni Homet, **Pablo Gálvez** y Chonghe Huang. Tutor: Jorge Saldivar.

**Mi aportación:** lideré la parte técnica de principio a fin junto con Antoni Homet: recogida de datos con Apify y reconstrucción de los hilos, embudo de limpieza, pipeline de anotación con Gemini y análisis estadístico.

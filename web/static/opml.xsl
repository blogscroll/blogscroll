<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
    <xsl:output method="html" encoding="UTF-8" indent="yes" />
    
    <xsl:template match="/">
        <html>
            <head>
                <title><xsl:value-of select="opml/head/title" /></title>
                <meta charset="UTF-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1.0" />
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        line-height: 1.6;
                        margin: 0;
                        padding: 20px;
                        background-color: #003049;
                        color: #fff;
                    }
                    .container {
                        max-width: 800px;
                        margin: 0 auto;
                    }
                    h1 {
                        color: #fcbf49;
                        border-bottom: 2px solid #fcbf49;
                        padding-bottom: 10px;
                    }
                    h2 {
                        color: #f77f00;
                        margin-top: 30px;
                    }
                    .info {
                        background-color: rgba(255, 255, 255, 0.1);
                        padding: 15px;
                        border-radius: 4px;
                        margin-bottom: 20px;
                    }
                    .download-link {
                        display: inline-block;
                        background-color: #f77f00;
                        color: #003049;
                        padding: 10px 20px;
                        text-decoration: none;
                        border-radius: 4px;
                        font-weight: bold;
                        margin: 10px 10px 10px 0;
                    }
                    .download-link:hover {
                        background-color: #fcbf49;
                    }
                    .category {
                        margin: 20px 0;
                    }
                    .blog-list {
                        list-style: none;
                        padding: 0;
                    }
                    .blog-item {
                        padding: 8px 0;
                        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                    }
                    .blog-item:last-child {
                        border-bottom: none;
                    }
                    .blog-link {
                        color: #eae2b7;
                        text-decoration: none;
                    }
                    .blog-link:hover {
                        color: #fcbf49;
                        text-decoration: underline;
                    }
                    .blog-count {
                        background-color: #f77f00;
                        color: #003049;
                        padding: 2px 6px;
                        border-radius: 4px;
                        font-size: 0.8em;
                        font-weight: bold;
                        margin-left: 8px;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1><xsl:value-of select="opml/head/title" /></h1>
                    
                    <div class="info">
                        <p><strong>What is this?</strong> This is an OPML file containing all the blogs from BlogScroll. You can import this into your RSS reader to subscribe to all these personal blogs and digital gardens.</p>
                        <p><strong>Generated:</strong> <xsl:value-of select="opml/head/dateCreated" /></p>
                        
                        <a href="/index.opml" class="download-link" download="blogscroll-blogs.opml">📥 Download OPML</a>
                        <a href="/" class="download-link">🏠 Back to BlogScroll</a>
                    </div>

                    <xsl:for-each select="opml/body/outline">
                        <div class="category">
                            <h2>
                                <xsl:value-of select="@text" />
                                <span class="blog-count"><xsl:value-of select="count(outline)" /></span>
                            </h2>
                            <ul class="blog-list">
                                <xsl:for-each select="outline">
                                    <li class="blog-item">
                                        <a href="{@htmlUrl}" class="blog-link" target="_blank">
                                            <xsl:value-of select="@text" />
                                        </a>
                                    </li>
                                </xsl:for-each>
                            </ul>
                        </div>
                    </xsl:for-each>
                </div>
            </body>
        </html>
    </xsl:template>
</xsl:stylesheet>

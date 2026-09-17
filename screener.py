export default {
    async fetch(request, env, ctx) {
        const url = new URL(request.url);
        const pathname = url.pathname;

        const corsHeaders = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        };

        if (request.method === 'OPTIONS') {
            return new Response(null, { headers: corsHeaders });
        }

        try {
            // --- ROUTE 1: Frontend reads today's screened stocks ---
            if (pathname === '/api/screener' && request.method === 'GET') {
                const { results } = await env.DB.prepare("SELECT * FROM screener_results ORDER BY rsi ASC").all();
                return Response.json(results, { headers: corsHeaders });
            }

            // --- ROUTE 2: Frontend reads historical chart data ---
            if (pathname.startsWith('/api/chart/') && request.method === 'GET') {
                const ticker = pathname.split('/api/chart/')[1];
                const { results } = await env.DB.prepare("SELECT date, close FROM historical_prices WHERE ticker = ? ORDER BY date ASC").bind(ticker).all();
                return Response.json(results, { headers: corsHeaders });
            }

            // --- ROUTE 3: Python pushes fundamental/technical data ---
            if (pathname === '/api/update-screener' && request.method === 'POST') {
                console.log("DEBUG: Received POST to /api/update-screener");
                
                // Auth check temporarily disabled for debugging
                // if (request.headers.get('Authorization') !== `Bearer ${env.GIT_SECRET}`) {
                //     return Response.json({ error: 'Unauthorized' }, { status: 401, headers: corsHeaders });
                // }

                const newData = await request.json();
                console.log("DEBUG: Received payload size:", newData.length, "stocks");

                const today = new Date().toISOString().split('T')[0];
                await env.DB.prepare("DELETE FROM screener_results WHERE date = ?").bind(today).run();

                // Batch insert for screener results
                const statements = newData.map(stock => 
                    env.DB.prepare(
                        `INSERT INTO screener_results (ticker, date, price, pe, roe, rsi, signal, target_mean, analyst_rec, num_analysts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
                    ).bind(stock.ticker, today, stock.price, stock.pe, stock.roe, stock.rsi, stock.signal, stock.target_mean, stock.analyst_rec, stock.num_analysts)
                );
                await env.DB.batch(statements);
                
                console.log("DEBUG: Successfully saved screener data to D1");
                return Response.json({ message: `Updated ${newData.length} stocks.` }, { headers: corsHeaders });
            }

            // --- ROUTE 4: Python pushes historical prices for charts ---
            if (pathname === '/api/update-history' && request.method === 'POST') {
                console.log("DEBUG: Received POST to /api/update-history");
                
                try {
                    const { ticker, data } = await request.json();
                    console.log(`DEBUG: Inserting ${data.length} days of history for ${ticker}`);
                    
                    // CRITICAL FIX: Chunk data into batches of 100 (Cloudflare D1 limit)
                    const chunks = [];
                    for (let i = 0; i < data.length; i += 100) {
                        chunks.push(data.slice(i, i + 100));
                    }

                    // Execute batches
                    for (const chunk of chunks) {
                        const statements = chunk.map(day => 
                            env.DB.prepare("INSERT OR IGNORE INTO historical_prices (ticker, date, close) VALUES (?, ?, ?)")
                                .bind(ticker, day.date, day.close)
                        );
                        await env.DB.batch(statements);
                    }
                    
                    console.log(`DEBUG: Successfully saved history for ${ticker}`);
                    return Response.json({ message: `Saved history for ${ticker}` }, { headers: corsHeaders });
                    
                } catch (err) {
                    console.error(`DEBUG: Error saving history for ${ticker}:`, err.message);
                    return Response.json({ message: `Error`, error: err.message }, { status: 200, headers: corsHeaders });
                }
            }

            return new Response('Not Found', { status: 404, headers: corsHeaders });

        } catch (err) {
            console.error("CRITICAL WORKER ERROR:", err);
            return Response.json({ error: err.message }, { status: 500, headers: corsHeaders });
        }
    }
};

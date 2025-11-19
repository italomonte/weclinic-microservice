"""
Script simples para visualizar o conteúdo do banco de dados.

Mostra estatísticas e últimos registros processados.
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def visualizar_banco():
    """Visualiza informações do banco de dados."""
    if not DATABASE_URL:
        print("❌ Erro: DATABASE_URL não configurada no .env")
        return
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        print("=" * 60)
        print("VISUALIZAÇÃO DO BANCO DE DADOS")
        print("=" * 60)
        
        # Estatísticas gerais
        cur.execute("SELECT COUNT(*) as total FROM processed")
        total = cur.fetchone()["total"]
        
        cur.execute("""
            SELECT COUNT(*) as hoje 
            FROM processed 
            WHERE DATE(criado_em) = CURRENT_DATE
        """)
        hoje = cur.fetchone()["hoje"]
        
        cur.execute("""
            SELECT tipo, COUNT(*) as count 
            FROM processed 
            GROUP BY tipo
        """)
        por_tipo = cur.fetchall()
        
        print(f"\n📊 ESTATÍSTICAS:")
        print(f"  Total de registros: {total}")
        print(f"  Registros de hoje: {hoje}")
        print(f"\n  Por tipo:")
        for row in por_tipo:
            print(f"    - {row['tipo']}: {row['count']}")
        
        # Últimos 20 registros
        print(f"\n📋 ÚLTIMOS 20 REGISTROS PROCESSADOS:")
        print("-" * 60)
        print(f"{'ID':<15} {'Tipo':<20} {'Criado em':<25}")
        print("-" * 60)
        
        cur.execute("""
            SELECT id, tipo, criado_em 
            FROM processed 
            ORDER BY criado_em DESC 
            LIMIT 20
        """)
        
        for row in cur.fetchall():
            id_str = str(row["id"])
            tipo_str = row["tipo"]
            data_str = row["criado_em"]
            print(f"{id_str:<15} {tipo_str:<20} {data_str:<25}")
        
        # Estatísticas por data
        print(f"\n📅 REGISTROS POR DATA (últimos 7 dias):")
        print("-" * 60)
        print(f"{'Data':<15} {'Quantidade':<15}")
        print("-" * 60)
        
        cur.execute("""
            SELECT DATE(criado_em) as data, COUNT(*) as count 
            FROM processed 
            WHERE DATE(criado_em) >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY DATE(criado_em)
            ORDER BY data DESC
        """)
        
        for row in cur.fetchall():
            print(f"{row['data']:<15} {row['count']:<15}")
        
        # Buscar por ID específico
        print(f"\n🔍 BUSCAR POR ID:")
        print("  Para buscar um ID específico, edite este script ou use SQL:")
        print(f'  psql "{DATABASE_URL}" -c "SELECT * FROM processed WHERE id = 123;"')
        
        conn.close()
        
        print("\n" + "=" * 60)
        print("💡 DICAS:")
        print("  - Use 'psql' para conectar ao PostgreSQL:")
        print(f"    psql \"{DATABASE_URL}\"")
        print("  - Ou use uma ferramenta gráfica como DBeaver, pgAdmin")
        print("  - Banco: PostgreSQL (Neon)")
        print("=" * 60)
        
    except psycopg2.OperationalError as e:
        if "does not exist" in str(e) or "relation" in str(e).lower():
            print("❌ Erro: Tabela 'processed' não existe.")
            print("   Execute o sistema pelo menos uma vez para criar o banco.")
        else:
            print(f"❌ Erro ao acessar banco: {e}")
            print("   Verifique se DATABASE_URL está correta no .env")
    except psycopg2.Error as e:
        print(f"❌ Erro ao acessar banco PostgreSQL: {e}")
        print("   Verifique se DATABASE_URL está correta no .env")


if __name__ == "__main__":
    visualizar_banco()


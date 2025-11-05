import sqlite3

conn = sqlite3.connect('instance/app.db')
cursor = conn.cursor()

print("="*90)
print("ONLINE SHOP - GL & TAX CHECK")
print("="*90)

print("\n1. Tax Settings:")
cursor.execute("SELECT key, value, description FROM system_settings WHERE key LIKE '%tax%' OR key LIKE '%vat%'")
tax_settings = cursor.fetchall()
if tax_settings:
    for s in tax_settings:
        print(f"  {s[0]}: {s[1]}")
        if s[2]:
            print(f"    Description: {s[2]}")
else:
    print("  No tax settings found in system_settings")

print("\n2. Product Tax Rates:")
cursor.execute("SELECT id, name, tax_rate, price, online_price FROM products WHERE tax_rate > 0 LIMIT 5")
products_with_tax = cursor.fetchall()
if products_with_tax:
    print("  Products with tax:")
    for p in products_with_tax:
        print(f"    Product {p[0]} ({p[1]}): tax={p[2]}%, price={p[3]}, online={p[4]}")
else:
    print("  No products with tax rate")

cursor.execute("SELECT COUNT(*) FROM products WHERE tax_rate > 0")
tax_count = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM products")
total_count = cursor.fetchone()[0]
print(f"  Total: {tax_count}/{total_count} products have tax rate")

print("\n3. OnlinePreOrder GL Batches:")
cursor.execute("""
    SELECT b.id, b.code, b.source_id, b.purpose, b.status, COUNT(e.id) as entries
    FROM gl_batches b
    LEFT JOIN gl_entries e ON e.batch_id = b.id
    WHERE b.source_type = 'ONLINE_ORDER'
    GROUP BY b.id
    ORDER BY b.id DESC
    LIMIT 5
""")
online_gl = cursor.fetchall()
if online_gl:
    print("  Online Order GL Batches:")
    for gl in online_gl:
        print(f"    Batch {gl[0]}: {gl[1]} - Order {gl[2]} - {gl[3]} - {gl[4]} ({gl[5]} entries)")
else:
    print("  No GL batches for online orders")

print("\n4. Payment GL Batches (for online shop):")
cursor.execute("""
    SELECT p.id, p.payment_number, p.total_amount, p.customer_id,
           p.reference, p.notes
    FROM payments p
    WHERE p.reference LIKE '%Online%' OR p.notes LIKE '%Online%'
    ORDER BY p.id DESC
    LIMIT 5
""")
online_payments = cursor.fetchall()

if online_payments:
    print("  Online Payments:")
    for pmt in online_payments:
        print(f"    Payment {pmt[0]} ({pmt[1]}): {pmt[2]} ILS, Customer {pmt[3]}")
        print(f"      Reference: {pmt[4]}")
        
        cursor.execute("""
            SELECT b.id, b.code, COUNT(e.id) as entries
            FROM gl_batches b
            LEFT JOIN gl_entries e ON e.batch_id = b.id
            WHERE b.source_type = 'PAYMENT' AND b.source_id = ?
            GROUP BY b.id
        """, (pmt[0],))
        
        pmt_gl = cursor.fetchall()
        if pmt_gl:
            for gl in pmt_gl:
                print(f"      GL Batch {gl[0]}: {gl[1]} ({gl[2]} entries)")
        else:
            print(f"      WARNING: No GL batch for this payment!")
else:
    print("  No online payments found")

print("\n5. OnlinePreOrder Data:")
cursor.execute("""
    SELECT id, order_number, customer_id, total_amount, prepaid_amount, 
           status, payment_status
    FROM online_preorders
    ORDER BY id DESC
    LIMIT 3
""")
orders = cursor.fetchall()
if orders:
    print("  Recent Online Orders:")
    for order in orders:
        print(f"    Order {order[0]} ({order[1]}): Customer {order[2]}")
        print(f"      Total: {order[3]}, Prepaid: {order[4]}")
        print(f"      Status: {order[5]}, Payment: {order[6]}")
else:
    print("  No online orders in database")

conn.close()

print("\n" + "="*90)
print("ANALYSIS SUMMARY")
print("="*90)


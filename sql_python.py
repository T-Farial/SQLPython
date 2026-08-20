import os
import sqlite3
import matplotlib.pyplot as plt
import pandas as pd
import requests

# 1. FETCH ARTWORK DATA FROM MET MUSEUM API
print("1. Fetching artwork records from The Met Museum API...")

departments = {
    11: "European Paintings",
    14: "Modern and Contemporary Art",
    4: "Asian Art",
}

departments_data = []
artists_data = []
artworks_data = []

for dept_id, dept_name in departments.items():
    departments_data.append((dept_id, dept_name))
    url = f"https://collectionapi.metmuseum.org/public/collection/v1/search?departmentId={dept_id}&hasImages=true&q=art"
    
    try:
        response = requests.get(url, timeout=10).json()
        object_ids = response.get("objectIDs", [])[:20]  # Top 20 items per department
    except Exception as err:
        print(f"Warning: Could not fetch ID list for department {dept_name} ({err})")
        continue

    for obj_id in object_ids:
        try:
            item = requests.get(
                f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{obj_id}",
                timeout=10,
            ).json()

            title = item.get("title") or "Untitled"
            artist_name = item.get("artistDisplayName") or "Unknown Artist"
            artist_bio = item.get("artistDisplayBio") or "N/A"
            creation_year = item.get("objectEndDate")
            medium = item.get("medium") or "Unknown Medium"
            country = item.get("country") or item.get("culture") or "Unknown Region"

            # Filter valid historical artwork entries
            if creation_year and creation_year > 0:
                artists_data.append((artist_name, artist_bio))
                artworks_data.append(
                    (
                        obj_id,
                        title,
                        artist_name,
                        dept_id,
                        creation_year,
                        medium,
                        country,
                    )
                )
        except Exception as err:
            print(f"Warning: Could not process artwork ID {obj_id} ({err})")
            continue

# 2. CONNECT TO SQLITE DATABASE & INSERT NEW DATA
print("\n2. Connecting to SQLite Database (preserving existing records)...")
db_file = "art_museum.db"

# Connects to existing DB file or creates a new one if missing
conn = sqlite3.connect(db_file)
cur = conn.cursor()

# Enable foreign key constraints
cur.execute("PRAGMA foreign_keys = ON;")

# Relational Schema - Only created if they don't exist
cur.execute(
    """
    CREATE TABLE IF NOT EXISTS departments (
        department_id INTEGER PRIMARY KEY,
        department_name TEXT NOT NULL
    )
"""
)

cur.execute(
    """
    CREATE TABLE IF NOT EXISTS artists (
        artist_name TEXT PRIMARY KEY,
        artist_bio TEXT
    )
"""
)

cur.execute(
    """
    CREATE TABLE IF NOT EXISTS artworks (
        object_id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        artist_name TEXT,
        department_id INTEGER,
        creation_year INTEGER,
        medium TEXT,
        country TEXT,
        FOREIGN KEY (artist_name) REFERENCES artists(artist_name),
        FOREIGN KEY (department_id) REFERENCES departments(department_id)
    )
"""
)

# Insert Data - IGNORE prevents primary key collision errors on existing rows
cur.executemany(
    "INSERT OR IGNORE INTO departments VALUES (?, ?)", departments_data
)
cur.executemany(
    "INSERT OR IGNORE INTO artists VALUES (?, ?)", artists_data
)
cur.executemany(
    "INSERT OR IGNORE INTO artworks VALUES (?, ?, ?, ?, ?, ?, ?)", artworks_data
)
conn.commit()
print("Database sync complete. Existing data preserved.")

# 3. SQL ANALYTICAL QUERIES
print("\n3. Executing SQL queries...\n")

# Query 1: Top Art Mediums (GROUP BY, COUNT, ORDER BY)
sql_mediums = """
    SELECT 
        medium, 
        COUNT(object_id) AS artwork_count
    FROM artworks
    WHERE medium != 'Unknown Medium'
    GROUP BY medium
    ORDER BY artwork_count DESC
    LIMIT 8;
"""

# Query 2: Century Distribution (GROUP BY, Aggregation)
sql_centuries = """
    SELECT 
        ((creation_year / 100) + 1) || 'th Century' AS century,
        COUNT(object_id) AS artwork_count
    FROM artworks
    GROUP BY century
    ORDER BY creation_year ASC;
"""

# Query 3: Department Summary (JOIN, COUNT, AVG)
sql_dept_summary = """
    SELECT 
        d.department_name,
        COUNT(a.object_id) AS total_artworks,
        COUNT(DISTINCT a.artist_name) AS total_artists,
        AVG(a.creation_year) AS avg_year
    FROM artworks a
    JOIN departments d ON a.department_id = d.department_id
    GROUP BY d.department_name;
"""

df_mediums = pd.read_sql_query(sql_mediums, conn)
df_centuries = pd.read_sql_query(sql_centuries, conn)
df_dept_summary = pd.read_sql_query(sql_dept_summary, conn)
conn.close()

# 4. PANDAS REPORTING
print("=" * 55)
print(" SQL REPORT 1: TOP ART MEDIUMS ")
print("=" * 55)
print(df_mediums.to_string(index=False))

print("\n" + "=" * 55)
print(" SQL REPORT 2: DEPARTMENT METRICS ")
print("=" * 55)
df_dept_summary["avg_year"] = df_dept_summary["avg_year"].round(0).astype(int)
print(df_dept_summary.to_string(index=False))

# 5. VISUALIZATIONS (Non-blocking file export)
print("\n4. Generating chart visualization...")
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Chart 1: Artworks by Medium
axes[0].barh(df_mediums["medium"], df_mediums["artwork_count"], color="#2c3e50")
axes[0].set_title("Top Artwork Mediums")
axes[0].set_xlabel("Number of Artworks")
axes[0].invert_yaxis()
axes[0].grid(axis="x", linestyle="--", alpha=0.5)

# Chart 2: Artworks per Century
axes[1].bar(df_centuries["century"], df_centuries["artwork_count"], color="#c0392b")
axes[1].set_title("Artworks Created per Century")
axes[1].set_ylabel("Number of Artworks")
axes[1].tick_params(axis="x", rotation=45)
axes[1].grid(axis="y", linestyle="--", alpha=0.5)

plt.tight_layout()
plt.savefig("art_museum_dashboard.png", dpi=300)
plt.close()
print("Success! Dashboard saved as 'art_museum_dashboard.png'.")
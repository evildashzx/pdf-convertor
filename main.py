#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Amazon Niche Premium Report Generator
Version 13.0 – ФИНАЛЬНАЯ РАБОЧАЯ ВЕРСИЯ
Основана на диагностике: PNG через BytesIO работает стабильно.
"""

import os
import sys
import argparse
import json
import re
import io
from collections import Counter
from datetime import datetime

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ========== CONFIG ==========
OWNER_NAME = "Your Name or Company"
LOGO_FILE = "logo.png"
REVIEW_TO_SALES_RATIO = 100
MONTHLY_REVIEW_RATIO = 0.05
STOPWORDS_BRAND = {'for', 'with', 'and', 'the', 'to', 'by', 'from', 'heated', 'cordless', 'shiatsu',
                   'massager', 'neck', 'shoulder', 'back', 'heat', 'electric', 'portable', 'gifts'}

# ========== TEXT CLEANING ==========
def clean_text(text):
    if not isinstance(text, str):
        return text
    replacements = {
        '“': '"', '”': '"', '‘': "'", '’': "'",
        '—': '-', '–': '-', '…': '...',
        '\u200e': '', '\u200f': '', '\u202a': '', '\u202b': '', '\u202c': '', '\u202d': '', '\u202e': ''
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return ''.join(c for c in text if ord(c) >= 32 or c in '\n\r\t')

def format_currency(value):
    if value >= 1e9:
        return f"${value/1e9:.1f}B"
    if value >= 1e6:
        return f"${value/1e6:.1f}M"
    if value >= 1e3:
        return f"${value/1e3:.0f}K"
    return f"${value:.0f}"

def format_number(value):
    try:
        return f"{int(value):,}"
    except:
        return str(value)

def truncate(text, max_len=20):
    if not isinstance(text, str):
        return str(text)
    if len(text) > max_len:
        return text[:max_len-3] + "..."
    return text

def extract_brand_from_title(title):
    if not isinstance(title, str):
        return "Unknown"
    words = title.split()
    for w in words[:3]:
        w_clean = w.strip('.,:;!?"\'()[]{}').capitalize()
        if len(w_clean) > 1 and w_clean.lower() not in STOPWORDS_BRAND:
            return w_clean
    return words[0].strip('.,:;!?"\'()[]{}').capitalize() if words else "Unknown"

# ========== DATA LOADING ==========
def load_data(input_dir):
    files = {
        'amazon_final': os.path.join(input_dir, 'amazon_final.csv'),
        'product_details': os.path.join(input_dir, 'product_details.csv'),
        'reviews': os.path.join(input_dir, 'reviews.csv'),
        'product_history': os.path.join(input_dir, 'product_history.csv'),
    }
    data = {}
    for key, path in files.items():
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                df.columns = df.columns.str.lower()
                print(f"Loaded {key}: {len(df)} rows")
                data[key] = df
            except Exception as e:
                print(f"Error loading {key}: {e}")
                data[key] = None
        else:
            print(f"File {key} not found, skipping.")
            data[key] = None

    if data['amazon_final'] is not None and 'asin' in data['amazon_final'].columns:
        df = data['amazon_final'].copy()
        df = df[df['asin'].notna() & (df['asin'] != '')]
        if 'position' in df.columns:
            df = df.sort_values('position')
        df = df.groupby('asin').first().reset_index()
        data['amazon_final'] = df
        print(f"After deduplication: {len(df)} unique ASINs")
    else:
        print("Error: amazon_final missing 'asin' column")
        return data

    data['brand_map'] = {}
    brand_sources = {'direct': 0, 'overview': 0, 'seller': 0, 'title': 0}

    if data['product_details'] is not None and 'asin' in data['product_details'].columns:
        has_brand_col = 'brand' in data['product_details'].columns
        for _, row in data['product_details'].iterrows():
            asin = row['asin']
            brand = None
            if has_brand_col and pd.notna(row.get('brand')):
                brand = str(row['brand']).strip()
                if brand and brand.lower() != 'nan':
                    brand_sources['direct'] += 1
            if not brand and 'product_overview' in row and pd.notna(row['product_overview']):
                try:
                    overview_str = row['product_overview'].replace("'", '"')
                    overview = json.loads(overview_str)
                    brand = overview.get('Brand')
                    if brand:
                        brand_sources['overview'] += 1
                except:
                    pass
            if not brand and 'seller' in row and pd.notna(row['seller']):
                seller = str(row['seller']).split()[0].capitalize()
                if seller and seller.lower() != 'nan':
                    brand = seller
                    brand_sources['seller'] += 1
            if brand:
                data['brand_map'][asin] = brand

    if data['amazon_final'] is not None:
        for _, row in data['amazon_final'].iterrows():
            asin = row['asin']
            if asin not in data['brand_map'] and 'title' in row and pd.notna(row['title']):
                brand = extract_brand_from_title(row['title'])
                data['brand_map'][asin] = brand
                brand_sources['title'] += 1

    print(f"Brand sources: direct={brand_sources['direct']}, overview={brand_sources['overview']}, "
          f"seller={brand_sources['seller']}, title={brand_sources['title']}")
    print(f"Total brands mapped: {len(data['brand_map'])}")

    if data['reviews'] is not None and 'helpful' in data['reviews'].columns:
        def parse_helpful(val):
            if pd.isna(val):
                return 0
            match = re.search(r'(\d+)', str(val))
            return int(match.group(1)) if match else 0
        data['reviews']['helpful_num'] = data['reviews']['helpful'].apply(parse_helpful)
        print("Helpful column normalized")

    return data

# ========== ANALYSIS FUNCTIONS ==========
def estimate_monthly_revenue(row):
    total_reviews = row['reviews_count'] if pd.notna(row['reviews_count']) else 0
    est_monthly_sales = total_reviews * REVIEW_TO_SALES_RATIO * MONTHLY_REVIEW_RATIO
    return est_monthly_sales * (row['price'] if pd.notna(row['price']) else 0)

def calculate_market_size(df_amazon):
    if df_amazon is None or df_amazon.empty:
        return 0
    total = 0
    for _, row in df_amazon.iterrows():
        total += estimate_monthly_revenue(row)
    return total

def competition_level_by_reviews(df_amazon):
    if df_amazon is None or df_amazon.empty or 'reviews_count' not in df_amazon.columns:
        return "Unknown", 0
    top10 = df_amazon.sort_values('position').head(10) if 'position' in df_amazon.columns else df_amazon.head(10)
    avg_reviews = top10['reviews_count'].mean()
    if avg_reviews > 2000:
        return "High", avg_reviews
    elif avg_reviews > 500:
        return "Medium", avg_reviews
    else:
        return "Low", avg_reviews

def saturation_index(df_amazon, brand_map):
    if df_amazon is None or df_amazon.empty:
        return 0
    df = df_amazon.copy()
    df['brand'] = df['asin'].map(brand_map).fillna('Unknown')
    brand_reviews = df.groupby('brand')['reviews_count'].sum().sort_values(ascending=False)
    total = brand_reviews.sum()
    if total == 0:
        return 0
    return (brand_reviews.head(3).sum() / total) * 100

def concentration_color(sat_score):
    if sat_score > 70:
        return "RED High Concentration"
    elif sat_score > 40:
        return "YELLOW Moderate Concentration"
    else:
        return "GREEN Low Concentration"

def keyword_competition(df_amazon):
    if df_amazon is None or df_amazon.empty:
        return "0%", "Unknown"
    sponsored_share = df_amazon['is_sponsored'].mean() * 100
    if sponsored_share > 40:
        comp = "Very High"
    elif sponsored_share > 25:
        comp = "High"
    elif sponsored_share > 15:
        comp = "Medium"
    else:
        comp = "Low"
    return f"{sponsored_share:.1f}%", comp

def determine_final_competition(avg_reviews_level, cr3):
    if cr3 > 70:
        return "Very High / Concentrated"
    elif cr3 > 50:
        if avg_reviews_level in ("High", "Medium"):
            return "High"
        else:
            return "Medium-High"
    else:
        return avg_reviews_level

# ========== REVIEW VELOCITY ==========
def compute_review_velocity(df_history):
    if df_history is None or df_history.empty:
        return {}
    df = df_history.copy()
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date', 'reviews_count'])
    df = df.sort_values(['asin', 'date'])

    velocities = {}
    for asin, group in df.groupby('asin'):
        if len(group) < 2:
            velocities[asin] = 0.0
            continue
        first = group.iloc[0]
        last = group.iloc[-1]
        days = (last['date'] - first['date']).days
        if days <= 0:
            velocities[asin] = 0.0
        else:
            growth = last['reviews_count'] - first['reviews_count']
            if growth < 0:
                growth = 0
            per_day = growth / days
            velocities[asin] = per_day * 30
    return velocities

# ========== REVIEW ANALYSIS ==========
def clean_review_text(text):
    if not isinstance(text, str):
        return ""
    text = re.sub(r'[^a-zA-Z\s]', ' ', text.lower())
    words = text.split()
    stopwords = set(['the', 'a', 'an', 'and', 'or', 'but', 'if', 'then', 'else', 'when',
                     'at', 'from', 'by', 'on', 'off', 'for', 'in', 'out', 'over', 'under',
                     'to', 'into', 'with', 'without', 'of', 'i', 'you', 'he', 'she', 'it',
                     'we', 'they', 'my', 'your', 'his', 'her', 'its', 'our', 'their',
                     'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has',
                     'had', 'do', 'does', 'did', 'will', 'would', 'shall', 'should', 'may',
                     'might', 'must', 'can', 'could', 'this', 'that', 'these', 'those',
                     'here', 'there', 'all', 'any', 'both', 'each', 'few', 'more', 'most',
                     'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so',
                     'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'get', 'got',
                     'use', 'used', 'using', 'one', 'two', 'new', 'also', 'well', 'even',
                     'back', 'time', 'like', 'make', 'made', 'much', 'many', 'still', 'even',
                     'really', 'pretty', 'little', 'lot', 'lots', 'great', 'good',
                     'nice', 'cute', 'love', 'amazing', 'awesome', 'perfect', 'easy'])
    filtered = [w for w in words if len(w) > 2 and w not in stopwords]
    return ' '.join(filtered)

def extract_pain_points_by_brand(df_reviews, brand_map, top_asins, top_n=3):
    if df_reviews is None or df_reviews.empty:
        return {}
    result = {}
    issue_keywords = {
        'Tarnishing / fading': ['tarnish', 'fade', 'color came off', 'rub off', 'wears off'],
        'Falling off': ['fell off', 'fall off', 'came off', 'loose', 'detach', 'pop off'],
        'Too sharp / snagging': ['sharp', 'scratch', 'snag', 'catch', 'poke', 'pain'],
        'Difficult to apply': ['hard to apply', 'difficult', 'tricky', 'fiddly', 'hard to pick'],
        'Small / size': ['too small', 'tiny', 'smaller than expected'],
        'Big / bulky': ['too big', 'bulky', 'thick', 'chunky'],
        'Quality issues': ['cheap', 'poor quality', 'broke', 'broken', 'cracked'],
        'Glue / adhesion': ['glue', 'stick', 'adhesive', 'hold'],
        'Packaging': ['packaging', 'spill', 'mix up', 'open', 'lid'],
    }
    for asin in top_asins[:3]:
        revs = df_reviews[df_reviews['asin'] == asin]
        if len(revs) == 0:
            continue
        neg_revs = revs[revs['rating'] <= 3]
        total_neg = len(neg_revs)
        if total_neg == 0:
            continue
        combined = ' '.join(neg_revs['text'].dropna().astype(str)).lower()
        issues = []
        for issue, keywords in issue_keywords.items():
            count = 0
            for kw in keywords:
                count += combined.count(kw)
            if count > 0:
                # Процент от общего числа негативных отзывов, но не более 100%
                pct = min(100, (count / total_neg) * 100)
                example = ""
                for txt in neg_revs['text'].dropna().astype(str)[:5]:
                    txt_low = txt.lower()
                    for kw in keywords:
                        if kw in txt_low:
                            example = txt[:150] + "..."
                            break
                    if example:
                        break
                if not example:
                    example = "(no example)"
                issues.append((issue, pct, example))
        issues.sort(key=lambda x: x[1], reverse=True)
        result[asin] = issues[:top_n]
    return result

# ========== CHARTS ==========
def create_scatter_revenue(df_amazon, brand_map):
    """Price vs Estimated Monthly Revenue (log scale) – возвращает BytesIO (PNG)"""
    if df_amazon is None or 'price' not in df_amazon.columns:
        return None
    df = df_amazon.copy()
    df['monthly_rev'] = df.apply(estimate_monthly_revenue, axis=1)
    df = df[df['monthly_rev'] > 0].dropna(subset=['price', 'monthly_rev'])
    if len(df) < 3:
        return None

    fig, ax = plt.subplots(figsize=(10, 6))
    scatter = ax.scatter(df['price'], df['monthly_rev'],
                         c=df['rating'] if 'rating' in df.columns else 'blue',
                         alpha=0.7, cmap='viridis', s=50, edgecolors='black', linewidth=0.5)
    ax.set_xlabel('Price ($)', fontsize=11)
    ax.set_ylabel('Monthly Revenue ($)', fontsize=11)  # убрали (log scale) – понятно по шкале
    ax.set_yscale('log')
    ax.set_title('Price vs. Estimated Monthly Revenue', fontsize=14, fontweight='bold')
    ax.grid(True, linestyle='--', alpha=0.3)
    if 'rating' in df.columns:
        cbar = plt.colorbar(scatter, label='Rating')
        cbar.ax.tick_params(labelsize=9)

    max_price_row = df.loc[df['price'].idxmax()]
    ax.annotate(f"{brand_map.get(max_price_row['asin'], '?')}\n${max_price_row['price']:.2f}",
                xy=(max_price_row['price'], max_price_row['monthly_rev']),
                xytext=(10, -20), textcoords='offset points',
                arrowprops=dict(arrowstyle='->', color='gray'),
                fontsize=9, bbox=dict(boxstyle='round,pad=0.3', fc='yellow', alpha=0.7))

    plt.tight_layout()
    img_data = io.BytesIO()
    fig.savefig(img_data, format='png', dpi=150, bbox_inches='tight')
    img_data.seek(0)
    plt.close(fig)
    return img_data

def create_reviews_histogram_clipped(df_amazon, clip_max=5000):
    """Histogram with median line – возвращает BytesIO (PNG)"""
    if df_amazon is None or 'reviews_count' not in df_amazon.columns:
        return None
    reviews = df_amazon['reviews_count'].dropna()
    outliers = reviews[reviews > clip_max]
    clipped = reviews[reviews <= clip_max]

    fig, ax = plt.subplots(figsize=(10,4))
    if len(clipped) > 0:
        ax.hist(clipped, bins=20, color='#1A4D8C', edgecolor='white', alpha=0.8)
    median_val = reviews.median()
    ax.axvline(median_val, color='red', linestyle='--', linewidth=1.5, label=f'Median: {median_val:.0f}')
    ax.set_xlabel('Number of Reviews', fontsize=11)
    ax.set_ylabel('Number of Products', fontsize=11)
    ax.set_title(f'Product Maturity Distribution (clipped at {clip_max} reviews)', fontsize=13, fontweight='bold')
    ax.grid(axis='y', linestyle='--', alpha=0.3)
    # Легенду в верхний правый угол
    ax.legend(loc='upper right')
    if len(outliers) > 0:
        text = f"{len(outliers)} product(s) have >{clip_max} reviews:\n" + ", ".join([f"{int(r):,}" for r in outliers[:5]])
        if len(outliers) > 5:
            text += f" and {len(outliers)-5} more"
        ax.text(0.98, 0.95, text, transform=ax.transAxes, ha='right', va='top',
                fontsize=9, bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    plt.tight_layout()
    img_data = io.BytesIO()
    fig.savefig(img_data, format='png', dpi=150, bbox_inches='tight')
    img_data.seek(0)
    plt.close(fig)
    return img_data

def create_heatmap(df_amazon):
    if df_amazon is None or len(df_amazon) < 3:
        return None
    num_cols = []
    if 'price' in df_amazon.columns:
        num_cols.append('price')
    if 'rating' in df_amazon.columns:
        num_cols.append('rating')
    if 'reviews_count' in df_amazon.columns:
        num_cols.append('reviews_count')
    if len(num_cols) < 2:
        return None
    corr = df_amazon[num_cols].corr()
    fig, ax = plt.subplots(figsize=(6,5))
    sns.heatmap(corr, annot=True, cmap='coolwarm', center=0, square=True,
                linewidths=1, cbar_kws={"shrink":0.8})
    ax.set_title('Correlation: Price, Rating & Reviews', fontweight='bold')
    plt.tight_layout()
    img_data = io.BytesIO()
    fig.savefig(img_data, format='png', dpi=150, bbox_inches='tight')
    img_data.seek(0)
    plt.close(fig)
    return img_data

def create_boxplot_horizontal(df_amazon, brand_map, top_n=8):
    """Horizontal boxplot – с ограничением оси X до $20, чтобы увидеть детали"""
    if df_amazon is None or 'price' not in df_amazon.columns:
        return None
    df = df_amazon.copy()
    df['brand'] = df['asin'].map(brand_map).fillna('Unknown')

    counts = df['brand'].value_counts()
    valid_brands = counts[counts >= 2].index.tolist()
    top_brands = valid_brands[:top_n]
    df['brand_for_plot'] = df['brand'].apply(lambda x: x if x in top_brands else 'Others')
    df_plot = df[df['brand_for_plot'].isin(top_brands + ['Others'])]

    if df_plot.empty:
        return None

    df_plot = df_plot.dropna(subset=['price'])

    brands_sorted = sorted(df_plot['brand_for_plot'].unique())
    if 'Others' in brands_sorted:
        brands_sorted.remove('Others')
        brands_sorted.append('Others')

    data_for_box = []
    for brand in brands_sorted:
        prices = df_plot[df_plot['brand_for_plot'] == brand]['price'].values
        if len(prices) > 0:
            data_for_box.append(prices)
        else:
            brands_sorted.remove(brand)

    fig, ax = plt.subplots(figsize=(10, 6))
    bp = ax.boxplot(data_for_box, vert=False, patch_artist=True, tick_labels=brands_sorted,
                    showmeans=True, meanline=True, medianprops={'color': 'red', 'linewidth': 2},
                    boxprops={'facecolor': 'lightblue', 'alpha': 0.6})
    ax.set_title('Price Distribution by Brand (at least 2 products, others grouped)', fontweight='bold')
    ax.set_xlabel('Price ($)')
    ax.set_ylabel('Brand')
    # Ограничиваем ось X, чтобы убрать выброс за $50
    ax.set_xlim(0, 20)
    ax.grid(True, axis='x', linestyle='--', alpha=0.3)

    plt.tight_layout()
    img_data = io.BytesIO()
    fig.savefig(img_data, format='png', dpi=150, bbox_inches='tight')
    img_data.seek(0)
    plt.close(fig)
    return img_data

# ========== PDF UTILS ==========
def add_page_number(canvas_obj, doc):
    page_num = canvas_obj.getPageNumber()
    canvas_obj.setFont('Helvetica', 9)
    canvas_obj.setFillColor(colors.grey)
    canvas_obj.drawRightString(20*cm, 0.5*cm, f"Page {page_num}")
    date_str = datetime.now().strftime('%d.%m.%Y')
    canvas_obj.drawString(1*cm, 0.5*cm, f"Market Data: {date_str} | Confidential Analysis")

# ========== PDF SECTIONS ==========
def create_title_page(elements, search_query, date_str, logo_path=None):
    styles = getSampleStyleSheet()
    elements.append(Spacer(1, 5*cm))
    if logo_path and os.path.exists(logo_path):
        try:
            img = Image(logo_path, width=4*cm, height=2.5*cm)
            img.hAlign = 'CENTER'
            elements.append(img)
            elements.append(Spacer(1, 1.5*cm))
        except:
            pass
    title_style = ParagraphStyle(
        'BigTitle',
        parent=styles['Title'],
        fontSize=36,
        textColor=colors.HexColor('#1A4D8C'),
        alignment=1,
        spaceAfter=20,
        fontName='Helvetica-Bold'
    )
    elements.append(Paragraph("Amazon Niche Analysis", title_style))
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=18,
        textColor=colors.HexColor('#666666'),
        alignment=1,
        spaceAfter=40
    )
    elements.append(Paragraph(f"Keyword: {search_query}", subtitle_style))
    elements.append(Spacer(1, 8*cm))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#999999'),
        alignment=1
    )
    elements.append(Paragraph(f"Prepared on {date_str} by {OWNER_NAME}", footer_style))
    elements.append(PageBreak())

def create_verdict_block(elements, cr3, avg_rating, sponsored_share, avg_reviews_level, final_competition):
    if cr3 > 70 or final_competition in ("Very High", "High"):
        verdict_text = "GO / NO-GO: HIGH RISK"
        bg_color = colors.HexColor('#D32F2F')
        sub_text = "Market is highly concentrated. Entry requires a unique advantage (patent / distinct form factor)."
    elif cr3 > 40 or avg_rating < 4.2 or sponsored_share > 30:
        verdict_text = "GO / NO-GO: MODERATE OPPORTUNITY"
        bg_color = colors.HexColor('#FBC02D')
        sub_text = "Some challenges exist, but a well-executed entry could succeed."
    else:
        verdict_text = "GO / NO-GO: ATTRACTIVE ENTRY"
        bg_color = colors.HexColor('#388E3C')
        sub_text = "Low concentration, healthy market – good time to launch."

    data = [[Paragraph(verdict_text,
                      ParagraphStyle('Verdict', fontSize=24, textColor=colors.white, alignment=1, fontName='Helvetica-Bold'))]]
    t = Table(data, colWidths=[16*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), bg_color),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 15),
        ('BOTTOMPADDING', (0,0), (-1,-1), 15),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('BOX', (0,0), (-1,-1), 0, colors.white),
        ('INNERGRID', (0,0), (-1,-1), 0, colors.white),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(sub_text,
                              ParagraphStyle('SubText', fontSize=11, textColor=colors.HexColor('#333333'), alignment=1)))
    elements.append(Spacer(1, 0.5*cm))

def create_summary(elements, df_amazon, df_details, brand_map, sat_score, final_competition):
    styles = getSampleStyleSheet()
    header = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontSize=16,
                            textColor=colors.HexColor('#1A4D8C'), spaceAfter=10)
    elements.append(Paragraph("Executive Summary", header))

    market_size = calculate_market_size(df_amazon)
    comp_reviews, avg_reviews = competition_level_by_reviews(df_amazon)
    sponsored_share, _ = keyword_competition(df_amazon)
    concentration = concentration_color(sat_score)

    prices = df_amazon['price'].dropna()
    price_range = f"${prices.quantile(0.25):.2f} – ${prices.quantile(0.75):.2f}" if len(prices) > 0 else "N/A"

    data = [
        ["Metric", "Value"],
        ["Unique Products", str(df_amazon['asin'].nunique())],
        ["Est. Monthly Revenue", format_currency(market_size)],
        ["Sponsored Share (Top50)", f"{df_amazon['is_sponsored'].mean()*100:.1f}%"],
        ["Avg Price", f"${df_amazon['price'].mean():.2f}"],
        ["Price Range (Q1-Q3)", price_range],  # более привычное обозначение
        ["Avg Rating", f"{df_amazon['rating'].mean():.2f}"],
        ["Avg Reviews (Top10)", f"{avg_reviews:,.0f}"],
        ["Competition (final)", final_competition],
        ["Saturation Index (CR3)", f"{sat_score:.1f}% ({concentration})"],
    ]
    if df_details is not None and 'is_fsa_eligible' in df_details.columns:
        fsa_pct = (df_details['is_fsa_eligible'].sum() / len(df_details)) * 100
        data.append(["FSA/HSA Eligible", f"{fsa_pct:.1f}%"])

    table = Table(data, colWidths=[6*cm, 5*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A4D8C')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 1, colors.grey),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 0.5*cm))

def create_top10_table(elements, df_amazon, brand_map, velocities, min_revenue=500):
    if df_amazon is None or 'position' not in df_amazon.columns:
        return
    styles = getSampleStyleSheet()
    header = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontSize=16,
                            textColor=colors.HexColor('#1A4D8C'), spaceAfter=10)
    elements.append(Paragraph("Top 10 Organic Competitors (Filtered, est. revenue > $500)", header))

    df_filtered = df_amazon.copy()
    df_filtered['est_rev'] = df_filtered.apply(estimate_monthly_revenue, axis=1)
    df_filtered = df_filtered[df_filtered['est_rev'] >= min_revenue]

    top10 = df_filtered.sort_values('position').head(10).copy()
    if len(top10) == 0:
        elements.append(Paragraph("No products with estimated revenue > $500.", styles['Normal']))
        return

    cell_style = ParagraphStyle(
        'CellStyle',
        fontSize=8,
        leading=10,
        wordWrap='CJK',
    )

    data = [["Pos", "Brand", "Price", "Rating", "Reviews", "Est. Monthly", "Sp", "Vel"]]
    for _, row in top10.iterrows():
        brand = brand_map.get(row['asin'], 'Unknown')
        sponsored = "✓" if row.get('is_sponsored', False) else ""
        price = f"${row['price']:.2f}" if pd.notna(row.get('price')) else 'N/A'
        rating = f"{row['rating']:.1f}" if pd.notna(row.get('rating')) else 'N/A'
        reviews = format_number(row['reviews_count']) if pd.notna(row.get('reviews_count')) else '0'
        monthly_rev = estimate_monthly_revenue(row)
        est_rev_str = format_currency(monthly_rev)
        velocity = velocities.get(row['asin'], 0)
        vel_str = f"{velocity:.1f}" if velocity > 0 else "-"
        data.append([
            str(int(row['position'])),
            Paragraph(truncate(brand, 16), cell_style),
            price,
            rating,
            reviews,
            est_rev_str,
            sponsored,
            vel_str
        ])

    table = Table(data, colWidths=[0.9*cm, 2.4*cm, 1.2*cm, 0.9*cm, 1.3*cm, 2.0*cm, 0.7*cm, 1.4*cm])
    style = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A4D8C')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('ALIGN', (1,1), (1,-1), 'LEFT'),
        ('ALIGN', (2,1), (-1,-1), 'RIGHT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 1, colors.grey),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]
    for i in range(1, len(data)):
        if data[i][6] == "✓":
            style.append(('BACKGROUND', (0,i), (-1,i), colors.HexColor('#FFF9C4')))
    table.setStyle(TableStyle(style))
    elements.append(table)
    elements.append(Spacer(1, 0.5*cm))

def create_advanced_review_insights(elements, df_reviews, brand_map, top_asins, pain_by_brand):
    if df_reviews is None or df_reviews.empty:
        return
    styles = getSampleStyleSheet()
    header = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontSize=16,
                            textColor=colors.HexColor('#1A4D8C'), spaceAfter=10)
    elements.append(Paragraph("Customer Feedback Analysis", header))

    if not pain_by_brand:
        elements.append(Paragraph("No significant negative feedback found.", styles['Normal']))
    else:
        for asin, issues in list(pain_by_brand.items())[:3]:
            brand = brand_map.get(asin, 'Unknown')
            elements.append(Paragraph(f"• {brand}", styles['Heading3']))
            if issues:
                data = [["Issue", "Freq", "Example"]]
                cell_style = ParagraphStyle(
                    'ExStyle',
                    fontSize=8,
                    wordWrap='CJK'
                )
                for issue, pct, example in issues:
                    data.append([issue, f"{pct:.0f}%", Paragraph(truncate(example, 40), cell_style)])
                tbl = Table(data, colWidths=[4*cm, 1.5*cm, 6*cm])
                tbl.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A4D8C')),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                    ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('GRID', (0,0), (-1,-1), 1, colors.grey),
                    ('TOPPADDING', (0,0), (-1,-1), 4),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ]))
                elements.append(tbl)
            else:
                elements.append(Paragraph("No significant complaints.", styles['Normal']))
            elements.append(Spacer(1, 0.3*cm))

        all_issues = []
        for asin, issues in pain_by_brand.items():
            all_issues.extend([issue for issue, _, _ in issues])
        if all_issues:
            top_issue = Counter(all_issues).most_common(1)[0][0]
            elements.append(Paragraph(f"<b>Conclusion:</b> Most common complaint is '{top_issue}'. Focus product improvement on this area (e.g., rounding edges, better coating).", styles['Normal']))
    elements.append(Spacer(1, 0.5*cm))

def create_dynamic_recommendations(elements, df_amazon, sat_score, avg_rating, sponsored_share,
                                   has_low_review_top, pain_by_brand):
    styles = getSampleStyleSheet()
    header = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontSize=16,
                            textColor=colors.HexColor('#1A4D8C'), spaceAfter=10)
    elements.append(Paragraph("Strategic Recommendations", header))

    recs = []

    if 'price' in df_amazon.columns:
        prices = df_amazon['price'].dropna()
        if len(prices) > 0:
            median_price = prices.median()
            q25, q75 = prices.quantile(0.25), prices.quantile(0.75)
            recs.append(f"Price range of successful products: ${q25:.2f} – ${q75:.2f} (median ${median_price:.2f}). Consider entering near this range.")
            top_prices = df_amazon.sort_values('price', ascending=False).head(5)['price'].values
            if len(top_prices) > 0 and top_prices[0] < median_price * 1.5:
                recs.append("Premium segment seems underdeveloped – opportunity for a higher‑priced quality option.")

    if sat_score > 70:
        recs.append("RED: Market is highly concentrated (top 3 brands >70% of reviews). Entry is risky; consider a distinct sub‑niche or patented feature.")
    elif sat_score > 50:
        recs.append("YELLOW: Moderate concentration. Differentiate with unique features to capture share.")
    else:
        recs.append("GREEN: Low concentration. Good opportunity for a new brand with quality positioning.")

    if avg_rating < 4.2:
        recs.append("Average rating below 4.2 – customers are dissatisfied. Opportunity for a higher‑quality product with better reviews.")

    if sponsored_share < 15:
        recs.append("Low PPC competition (<15% sponsored). Aggressive advertising can be cost‑effective.")
    elif sponsored_share > 30:
        recs.append("High PPC competition. Focus on organic ranking and strong listing optimization.")

    if has_low_review_top:
        recs.append("Top 10 contains products with <200 reviews – market entry appears feasible (low review barrier).")

    all_issues = []
    for asin, issues in pain_by_brand.items():
        all_issues.extend([issue for issue, _, _ in issues])
    if all_issues:
        top_issue = Counter(all_issues).most_common(1)[0][0]
        recs.append(f"Most common complaint: '{top_issue}'. Address this in your product design to stand out.")

    if len(recs) < 3:
        recs.append("Focus on clear product images and highlight the variety/sizes included.")
        recs.append("Emphasize durability and easy application in your marketing.")

    for r in recs:
        # Исправляем возможный спецсимвол sub‑niche
        r = r.replace('sub‑niche', 'sub-niche')
        elements.append(Paragraph(f"• {r}", styles['Normal']))
    elements.append(Spacer(1, 0.5*cm))

# ========== MAIN ==========
def generate_report(input_dir, output_file):
    print("="*60)
    print("PREMIUM AMAZON REPORT GENERATOR v13.0 – ФИНАЛЬНАЯ ВЕРСИЯ")
    print("="*60)
    if not os.path.isdir(input_dir):
        print(f"Error: folder '{input_dir}' not found.")
        return
    data = load_data(input_dir)
    df_amazon = data.get('amazon_final')
    df_details = data.get('product_details')
    df_reviews = data.get('reviews')
    df_history = data.get('product_history')
    brand_map = data.get('brand_map', {})
    if df_amazon is None or df_amazon.empty:
        print("No amazon_final data. Cannot generate report.")
        return
    if 'asin' not in df_amazon.columns:
        print("Error: 'asin' column missing in amazon_final.")
        return

    velocities = compute_review_velocity(df_history)

    search_query = df_amazon['search_query'].iloc[0] if 'search_query' in df_amazon.columns else 'N/A'
    date_str = datetime.now().strftime("%d.%m.%Y")
    sat_score = saturation_index(df_amazon, brand_map)
    logo_path = os.path.join(input_dir, LOGO_FILE) if os.path.exists(os.path.join(input_dir, LOGO_FILE)) else None

    comp_reviews, avg_reviews = competition_level_by_reviews(df_amazon)
    final_competition = determine_final_competition(comp_reviews, sat_score)

    sponsored_share = df_amazon['is_sponsored'].mean() * 100 if 'is_sponsored' in df_amazon.columns else 0
    avg_rating = df_amazon['rating'].mean() if 'rating' in df_amazon.columns else 0

    has_low_review_top = False
    if 'position' in df_amazon.columns and 'reviews_count' in df_amazon.columns:
        top10 = df_amazon.sort_values('position').head(10)
        low_review_count = (top10['reviews_count'] < 200).sum()
        if low_review_count >= 2:
            has_low_review_top = True

    top_asins = df_amazon.sort_values('position').head(10)['asin'].tolist() if 'position' in df_amazon.columns else []
    pain_by_brand = extract_pain_points_by_brand(df_reviews, brand_map, top_asins)

    doc = SimpleDocTemplate(output_file, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    elements = []

    create_title_page(elements, search_query, date_str, logo_path)
    create_verdict_block(elements, sat_score, avg_rating, sponsored_share, comp_reviews, final_competition)
    create_summary(elements, df_amazon, df_details, brand_map, sat_score, final_competition)

    elements.append(PageBreak())
    elements.append(Paragraph("Visual Analysis", ParagraphStyle('SectionHeader', fontSize=16,
                                                                 textColor=colors.HexColor('#1A4D8C'), spaceAfter=10)))

    sp = create_scatter_revenue(df_amazon, brand_map)
    if sp:
        elements.append(Image(sp, width=14*cm, height=8*cm))
        elements.append(Spacer(1, 0.5*cm))

    hist = create_reviews_histogram_clipped(df_amazon, clip_max=5000)
    if hist:
        elements.append(Image(hist, width=14*cm, height=6*cm))
        elements.append(Spacer(1, 0.5*cm))

    hm = create_heatmap(df_amazon)
    if hm:
        elements.append(Image(hm, width=12*cm, height=10*cm))
        elements.append(Spacer(1, 0.5*cm))

    bp = create_boxplot_horizontal(df_amazon, brand_map)
    if bp:
        elements.append(Image(bp, width=14*cm, height=8*cm))
        elements.append(Spacer(1, 0.5*cm))

    elements.append(PageBreak())
    create_top10_table(elements, df_amazon, brand_map, velocities, min_revenue=500)

    create_advanced_review_insights(elements, df_reviews, brand_map, top_asins, pain_by_brand)
    create_dynamic_recommendations(elements, df_amazon, sat_score, avg_rating, sponsored_share,
                                   has_low_review_top, pain_by_brand)

    doc.build(elements, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f"\nReport successfully generated: {output_file}")
    print("="*60)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='data', help='Input folder (default: ./data)')
    parser.add_argument('--output', default='premium_report.pdf', help='Output PDF filename')
    args = parser.parse_args()
    generate_report(args.input, args.output)

if __name__ == '__main__':
    main()
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
import urllib.request
from collections import Counter
from datetime import datetime

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FuncFormatter

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.utils import ImageReader

# ========== CONFIG ==========
OWNER_NAME = "Your Name or Company"
LOGO_FILE = "logo.png"
CURRENT_LOGO_PATH = None
REVIEW_TO_SALES_RATIO = 100
MONTHLY_REVIEW_RATIO = 0.05

STOPWORDS_BRAND = set(['the', 'and', 'for', 'with', 'new', 'from', 'this', 'that', 'amazon', 'com', 'www', 'http', 'https'])
GENERIC_BRANDS = {'', 'generic', 'n/a', 'na', 'none', 'unknown', 'unbranded'}

# ========== HELPER FUNCTIONS ==========
def format_currency(value):
    try:
        return f"${value:,.0f}"
    except:
        return f"${value}"

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

def format_compact_currency(value):
    try:
        value = float(value)
    except Exception:
        return format_currency(value)
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.0f}"

def normalize_brand(value):
    if not isinstance(value, str):
        return 'Generic / N/A'
    cleaned = value.strip()
    if cleaned.lower() in GENERIC_BRANDS:
        return 'Generic / N/A'
    return cleaned

def extract_brand_from_title(title):
    if not isinstance(title, str):
        return "Unknown"
    words = title.split()
    for w in words[:3]:
        w_clean = w.strip('.,:;!?"\'()[]{}').capitalize()
        if len(w_clean) > 1 and w_clean.lower() not in STOPWORDS_BRAND:
            return w_clean
    return words[0].strip('.,:;!?"\'()[]{}').capitalize() if words else "Unknown"

def fetch_image_bytes(url, timeout=8):
    if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
        return None
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            content = response.read()
            if content:
                return io.BytesIO(content)
    except Exception:
        return None
    return None

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
        before = len(df)
        df = df.dropna(subset=['asin'])
        df = df.drop_duplicates(subset=['asin'], keep='first').reset_index(drop=True)
        if len(df) != before:
            print(f"Removed {before - len(df)} duplicated rows by ASIN")
        data['amazon_final'] = df

        data['brand_map'] = {}
        has_brand_col = 'brand' in df.columns
        for _, row in df.iterrows():
            brand = None
            if has_brand_col and pd.notna(row.get('brand')):
                brand = normalize_brand(str(row.get('brand')))
            if not brand or brand == 'Generic / N/A':
                if pd.notna(row.get('title')):
                    fallback = extract_brand_from_title(row['title'])
                    brand = normalize_brand(fallback)
                else:
                    brand = 'Generic / N/A'
            data['brand_map'][row['asin']] = brand
    else:
        data['brand_map'] = {}

    return data

# ========== METRICS ==========
def estimate_monthly_revenue(row):
    reviews = row.get('reviews_count', 0)
    if pd.isna(reviews) or reviews == 0:
        return 0
    sales = reviews * REVIEW_TO_SALES_RATIO
    price = row.get('price', 0)
    if pd.isna(price):
        return 0
    monthly_rev = sales * price * MONTHLY_REVIEW_RATIO
    return max(0, monthly_rev)

def calculate_market_size(df_amazon):
    total = 0
    for _, row in df_amazon.iterrows():
        total += estimate_monthly_revenue(row)
    return total

def saturation_index(df_amazon, brand_map):
    if df_amazon is None or 'reviews_count' not in df_amazon.columns:
        return 0
    df = df_amazon.copy()
    df['brand'] = df['asin'].map(brand_map).fillna('Unknown')
    brand_reviews = df.groupby('brand')['reviews_count'].sum().sort_values(ascending=False)
    top3_sum = brand_reviews.head(3).sum()
    total = brand_reviews.sum()
    if total == 0:
        return 0
    return (top3_sum / total) * 100

def competition_level_by_reviews(df_amazon):
    if df_amazon is None or 'reviews_count' not in df_amazon.columns:
        return "Unknown", 0
    reviews = df_amazon['reviews_count'].dropna()
    if len(reviews) == 0:
        return "Unknown", 0
    avg_reviews = reviews.mean()
    if avg_reviews < 200:
        return "Low", avg_reviews
    elif avg_reviews < 1000:
        return "Medium", avg_reviews
    else:
        return "High", avg_reviews

def keyword_competition(df_amazon):
    if df_amazon is None or 'is_sponsored' not in df_amazon.columns:
        return 0, "Unknown"
    sponsored_pct = df_amazon['is_sponsored'].mean() * 100
    if sponsored_pct < 20:
        level = "Low"
    elif sponsored_pct < 40:
        level = "Medium"
    else:
        level = "High"
    return sponsored_pct, level

def determine_final_competition(comp_reviews, sat_score):
    if sat_score > 70 or comp_reviews == "High":
        return "Very High"
    elif sat_score > 50 or comp_reviews == "Medium":
        return "High"
    else:
        return "Medium"

def concentration_color(sat_score):
    if sat_score > 70:
        return "Very High"
    elif sat_score > 50:
        return "High"
    else:
        return "Medium"

def compute_review_velocity(df_history):
    velocities = {}
    if df_history is None or 'asin' not in df_history.columns or 'date' not in df_history.columns or 'reviews' not in df_history.columns:
        return velocities
    df = df_history.copy()
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(['asin', 'date'])
    for asin, group in df.groupby('asin'):
        if len(group) >= 2:
            first = group.iloc[0]
            last = group.iloc[-1]
            days = (last['date'] - first['date']).days
            if days > 0:
                vel = (last['reviews'] - first['reviews']) / days
                velocities[asin] = max(0, vel)
    return velocities

# ========== REVIEW ANALYSIS ==========
def clean_review_text(text):
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r'[^a-z\s]', '', text)
    words = text.split()
    stopwords = set(['i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your', 'yours',
                     'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her', 'hers',
                     'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 'theirs', 'themselves',
                     'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'is', 'are',
                     'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'having', 'do', 'does',
                     'did', 'doing', 'a', 'an', 'the', 'and', 'but', 'if', 'or', 'because', 'as', 'until',
                     'while', 'of', 'at', 'by', 'for', 'with', 'about', 'against', 'between', 'into',
                     'through', 'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up', 'down',
                     'in', 'out', 'on', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here',
                     'there', 'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more',
                     'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so',
                     'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'don', 'should', 'now'])
    filtered = [w for w in words if w not in stopwords and len(w) > 2]
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
        review_texts = neg_revs['text'].dropna().astype(str).tolist()
        issues = []
        for issue, keywords in issue_keywords.items():
            mention_count = 0
            for txt in review_texts:
                txt_low = txt.lower()
                if any(kw in txt_low for kw in keywords):
                    mention_count += 1
            if mention_count > 0:
                pct = (mention_count / total_neg) * 100
                example = ""
                for txt in review_texts[:5]:
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
def create_scatter_revenue(df_amazon, brand_map, max_price=20):
    """Price vs Estimated Monthly Revenue (log scale) – возвращает BytesIO (PNG) и DataFrame выбросов"""
    if df_amazon is None or 'price' not in df_amazon.columns:
        return None, None
    df = df_amazon.copy()
    df['monthly_rev'] = df.apply(estimate_monthly_revenue, axis=1)
    df = df[df['monthly_rev'] > 0].dropna(subset=['price', 'monthly_rev'])
    if len(df) < 3:
        return None, None

    outliers = df[df['price'] > max_price].sort_values('price', ascending=False)
    df_plot = df[df['price'] <= max_price]
    if len(df_plot) < 3:
        return None, outliers

    premium_cmap = LinearSegmentedColormap.from_list('premium_gold_navy', ['#D4AF37', '#0D1B2A'])

    fig, ax = plt.subplots(figsize=(10,6))
    scatter = ax.scatter(df_plot['price'], df_plot['monthly_rev'],
                         c=df_plot['price'], cmap=premium_cmap, alpha=0.78,
                         edgecolors='w', linewidth=0.5, s=50)
    ax.set_yscale('log')
    ax.set_xlabel('Price ($)', fontsize=12)
    ax.set_ylabel('Est. Monthly Revenue ($, log scale)', fontsize=12)
    ax.set_title(f'Price vs. Estimated Monthly Revenue (up to ${max_price})', fontweight='bold')
    ax.grid(True, linestyle='--', alpha=0.3)
    ax.set_xlim(0, max_price)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{int(y):,}" if y >= 1 else f"{y:g}"))

    max_price_row = df_plot.loc[df_plot['price'].idxmax()]
    ax.annotate(f"{brand_map.get(max_price_row['asin'], '?')}\n${max_price_row['price']:.2f}",
                xy=(max_price_row['price'], max_price_row['monthly_rev']),
                xytext=(10, -20), textcoords='offset points',
                arrowprops=dict(arrowstyle='->', color='#263238', lw=1.2),
                fontsize=9, color='#111111',
                bbox=dict(boxstyle='round,pad=0.35', fc='white', ec='#0D1B2A', lw=1.2, alpha=0.92))
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label('Price tier')

    plt.tight_layout()
    img_data = io.BytesIO()
    fig.savefig(img_data, format='png', dpi=150, bbox_inches='tight')
    img_data.seek(0)
    plt.close(fig)
    return img_data, outliers

def create_reviews_histogram_clipped(df_amazon, clip_max=5000):
    """Histogram with median line – возвращает BytesIO (PNG)"""
    if df_amazon is None or 'reviews_count' not in df_amazon.columns:
        return None
    reviews = df_amazon['reviews_count'].dropna()
    outliers = reviews[reviews > clip_max]
    clipped = reviews[reviews <= clip_max]

    fig, ax = plt.subplots(figsize=(10,4))
    if len(clipped) > 0:
        ax.hist(clipped, bins=20, color='#1A4D8C', edgecolor='white', alpha=0.8, zorder=2)
    median_val = reviews.median()
    ax.axvline(median_val, color='red', linestyle='--', linewidth=1.5, label=f'Median: {median_val:.0f}', zorder=5)
    ax.set_xlabel('Number of Reviews', fontsize=11)
    ax.set_ylabel('Number of Products', fontsize=11)
    ax.set_title(f'Product Maturity Distribution (clipped at {clip_max} reviews)', fontsize=13, fontweight='bold')
    ax.grid(axis='y', linestyle='--', alpha=0.3)
    ax.legend(loc='lower right', fontsize=8, framealpha=0.85)
    if len(outliers) > 0:
        text = f"{len(outliers)} product(s) have >{clip_max} reviews:\n" + ", ".join([f"{int(r):,}" for r in outliers[:5]])
        if len(outliers) > 5:
            text += f" and {len(outliers)-5} more"
        ax.text(0.98, 0.18, text, transform=ax.transAxes, ha='right', va='bottom',
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
    tick_values = np.linspace(-1, 1, 9)
    sns.heatmap(corr, annot=True, cmap='coolwarm', center=0, ax=ax, square=True,
                cbar_kws={'ticks': tick_values})
    ax.set_title('Correlation Heatmap', fontweight='bold')
    ax.text(0.5, 1.02, 'Price vs. Rating vs. Reviews Count', transform=ax.transAxes,
            ha='center', va='bottom', fontsize=9, color='#546E7A')
    plt.tight_layout()
    img_data = io.BytesIO()
    fig.savefig(img_data, format='png', dpi=150, bbox_inches='tight')
    img_data.seek(0)
    plt.close(fig)
    return img_data

def create_boxplot_horizontal(df_amazon, brand_map, top_n=5):
    if df_amazon is None or 'price' not in df_amazon.columns or 'asin' not in df_amazon.columns:
        return None
    df = df_amazon.copy()
    df['brand'] = df['asin'].map(brand_map).fillna('Generic / N/A')
    df = df.dropna(subset=['price'])
    if df.empty:
        return None

    top_brands = df['brand'].value_counts().head(top_n).index.tolist()
    df['brand_for_plot'] = df['brand'].apply(lambda x: x if x in top_brands else 'Other Brands')
    df_plot = df[df['brand_for_plot'].notna() & (df['brand_for_plot'] != '')]
    if len(df_plot) < 5:
        return None

    brands_sorted = [b for b in top_brands if b in df_plot['brand_for_plot'].unique()]
    if 'Other Brands' in df_plot['brand_for_plot'].unique():
        brands_sorted.append('Other Brands')

    representative_asin = {
        brand: df_plot[df_plot['brand_for_plot'] == brand]['asin'].iloc[0]
        for brand in brands_sorted
        if len(df_plot[df_plot['brand_for_plot'] == brand]) > 0
    }

    data_for_box = []
    clean_labels = []
    for brand in brands_sorted:
        prices = df_plot[df_plot['brand_for_plot'] == brand]['price'].values
        if len(prices) >= 2:
            data_for_box.append(prices)
            asin_tail = representative_asin.get(brand, '')[-4:]
            clean_labels.append(f"{brand} ({asin_tail})" if asin_tail else brand)

    if len(data_for_box) < 2:
        return None

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.boxplot(
        data_for_box,
        vert=False,
        patch_artist=True,
        tick_labels=clean_labels,
        showmeans=True,
        meanline=True,
        medianprops={'color': '#0D47A1', 'linewidth': 2},
        boxprops={'facecolor': '#D7ECFF', 'edgecolor': '#1E88E5', 'alpha': 0.85},
        whiskerprops={'color': '#455A64', 'linewidth': 1.2},
        capprops={'color': '#455A64', 'linewidth': 1.2},
    )
    ax.set_title('Price Distribution by Brand (Top 5 + Other Brands)', fontweight='bold')
    ax.set_xlabel('Price ($)')
    ax.set_ylabel('Brand')
    ax.grid(True, axis='x', linestyle='--', alpha=0.45)

    plt.tight_layout()
    img_data = io.BytesIO()
    fig.savefig(img_data, format='png', dpi=150, bbox_inches='tight')
    img_data.seek(0)
    plt.close(fig)
    return img_data

# ========== PDF UTILS ==========
def add_page_number(canvas_obj, doc):
    global CURRENT_LOGO_PATH
    canvas_obj.saveState()
    canvas_obj.setStrokeColor(colors.HexColor('#B0BEC5'))
    canvas_obj.setLineWidth(0.8)
    canvas_obj.rect(0.8*cm, 0.8*cm, A4[0]-1.6*cm, A4[1]-1.6*cm)
    canvas_obj.setFillColor(colors.HexColor('#ECEFF1'))
    for x in np.arange(1.2*cm, A4[0]-1.2*cm, 2.2*cm):
        canvas_obj.circle(x, A4[1]-1.2*cm, 0.03*cm, stroke=0, fill=1)
    page_num = canvas_obj.getPageNumber()
    canvas_obj.setFont('Helvetica', 9)
    canvas_obj.setFillColor(colors.grey)
    canvas_obj.drawRightString(20*cm, 0.5*cm, f"Page {page_num}")
    date_str = datetime.now().strftime('%d.%m.%Y')
    canvas_obj.drawString(1*cm, 0.5*cm, f"Market Data: {date_str} | Confidential Analysis")
    if CURRENT_LOGO_PATH and os.path.exists(CURRENT_LOGO_PATH):
        try:
            logo_reader = ImageReader(CURRENT_LOGO_PATH)
            canvas_obj.drawImage(logo_reader, A4[0] - 3.4*cm, 0.28*cm, width=2.0*cm, height=0.5*cm,
                                 preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    canvas_obj.restoreState()

# ========== PDF SECTIONS ==========
def create_title_page(elements, search_query, date_str, logo_path=None, product_image=None):
    styles = getSampleStyleSheet()
    elements.append(Spacer(1, 3.2*cm))
    elements.append(Paragraph("Amazon Niche Analysis", ParagraphStyle(
        'BigTitle', parent=styles['Title'], fontSize=36, textColor=colors.HexColor('#1A4D8C'),
        alignment=1, spaceAfter=16, fontName='Helvetica-Bold'
    )))
    keyword_style = ParagraphStyle(
        'KeywordFocus', parent=styles['Normal'], fontSize=24,
        textColor=colors.HexColor('#123A6F'), alignment=1, spaceAfter=26, fontName='Helvetica-Bold'
    )
    elements.append(Paragraph(f"<b>{search_query}</b>", ParagraphStyle('KeywordFocusXL', parent=keyword_style, fontSize=36, spaceAfter=10)))
    elements.append(Paragraph("Detailed Market Landscape &amp; Entry Strategy", ParagraphStyle(
        'Subtitle', parent=styles['Normal'], fontSize=12, alignment=1, textColor=colors.HexColor('#455A64'), spaceAfter=18
    )))

    inserted_image = False
    if logo_path and os.path.exists(logo_path):
        try:
            img = Image(logo_path, width=6*cm, height=3.5*cm)
            img.hAlign = 'CENTER'
            elements.append(img)
            inserted_image = True
        except Exception:
            inserted_image = False
    elif product_image:
        try:
            img = Image(product_image, width=6*cm, height=3.5*cm)
            img.hAlign = 'CENTER'
            elements.append(img)
            inserted_image = True
        except Exception:
            inserted_image = False
    if not inserted_image:
        visual_markup = "<para align='center'><font size='30' color='#1A4D8C'>✦</font><br/><font size='11' color='#455A64'>Niche emblem</font></para>"
        placeholder = Table([[Paragraph(visual_markup, styles['Normal'])]], colWidths=[7*cm], rowHeights=[4.2*cm])
        placeholder.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#90A4AE')),
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F5F7FA')),
            ('TEXTCOLOR', (0,0), (-1,-1), colors.HexColor('#607D8B')),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
        ]))
        elements.append(placeholder)

    elements.append(Spacer(1, 6.2*cm))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#999999'),
        alignment=1
    )
    elements.append(Spacer(1, 1.2*cm))
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
                       ParagraphStyle('Verdict', fontSize=14, textColor='white', alignment=1, fontName='Helvetica-Bold'))]]
    t = Table(data, colWidths=[16*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), bg_color),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 12),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(sub_text, ParagraphStyle('SubVerdict', fontSize=10, textColor=colors.HexColor('#555555'), alignment=1)))
    elements.append(Spacer(1, 0.8*cm))

def create_summary(elements, df_amazon, df_details, brand_map, sat_score, final_competition):
    styles = getSampleStyleSheet()
    header = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontSize=16,
                            textColor=colors.HexColor('#1A4D8C'), spaceAfter=10)
    elements.append(Paragraph("Market Summary", header))

    market_size = calculate_market_size(df_amazon)
    comp_reviews, avg_reviews = competition_level_by_reviews(df_amazon)
    sponsored_share, _ = keyword_competition(df_amazon)
    concentration = concentration_color(sat_score)

    prices = df_amazon['price'].dropna()
    price_range = f"${prices.quantile(0.25):.2f} – ${prices.quantile(0.75):.2f}" if len(prices) > 0 else "N/A"

    data = [
        ["Metric", "Value"],
        ["Unique Products", str(df_amazon['asin'].nunique())],
        ["Est. Monthly Revenue", format_compact_currency(market_size)],
        ["Sponsored Share (Top50)", f"{df_amazon['is_sponsored'].mean()*100:.1f}%"],
        ["Avg Price", f"${df_amazon['price'].mean():.2f}"],
        ["Price Range (Q1-Q3)", price_range],
        ["Avg Rating", f"{df_amazon['rating'].mean():.2f}"],
        ["Avg Reviews (Top10)", f"{avg_reviews:,.0f}"],
        ["Competition (final)", final_competition],
        ["Saturation Index (CR3)", f"{sat_score:.1f}%"],
        ["Avg. Revenue per Listing", format_compact_currency(market_size / max(1, df_amazon['asin'].nunique()))],
    ]
    if df_details is not None and 'is_fsa_eligible' in df_details.columns:
        fsa_pct = (df_details['is_fsa_eligible'].sum() / len(df_details)) * 100
        data.append(["FSA/HSA Eligible", f"{fsa_pct:.1f}%"])

    table = Table(data, colWidths=[5.6*cm, 5.8*cm])
    style = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A4D8C')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 1, colors.grey),
        ('TOPPADDING', (0,0), (-1,-1), 9),
        ('BOTTOMPADDING', (0,0), (-1,-1), 9),
    ]
    for row_idx, row in enumerate(data[1:], start=1):
        if row[0] == "Saturation Index (CR3)" and sat_score > 70:
            style.extend([
                ('BACKGROUND', (0, row_idx), (1, row_idx), colors.HexColor('#FFCDD2')),
                ('TEXTCOLOR', (0, row_idx), (1, row_idx), colors.HexColor('#B71C1C')),
                ('FONTNAME', (0, row_idx), (1, row_idx), 'Helvetica-Bold')
            ])
    table.setStyle(TableStyle(style))
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

    has_velocity_data = any(v > 0 for v in velocities.values())
    lqs_scores = []
    for _, row in top10.iterrows():
        image_count = row.get('image_count', np.nan)
        if pd.isna(image_count):
            image_count = row.get('images_count', np.nan)
        has_video = bool(row.get('has_video', False))
        has_aplus = bool(row.get('has_aplus', row.get('has_a_plus', False)))
        lqs_score = 40
        if pd.notna(image_count):
            lqs_score += min(30, float(image_count) * 3)
        if has_video:
            lqs_score += 15
        if has_aplus:
            lqs_score += 15
        lqs_scores.append(min(100, int(lqs_score)))

    include_lqs = len(set(lqs_scores)) > 1
    data = [["Pos", "ASIN", "Brand", "Price", "Rating", "Reviews", "Est. Monthly Sp", "Traffic"]]
    if include_lqs:
        data[0].insert(7, "LQS")
    if has_velocity_data:
        data[0].append("Vel")
    best_eff_row_idx = None
    best_efficiency = -1
    for idx, (_, row) in enumerate(top10.iterrows()):
        brand = brand_map.get(row['asin'], 'Unknown')
        sponsored = bool(row.get('is_sponsored', False))
        price = f"${row['price']:.2f}" if pd.notna(row.get('price')) else 'N/A'
        rating = f"{row['rating']:.1f}" if pd.notna(row.get('rating')) else 'N/A'
        reviews = format_number(row['reviews_count']) if pd.notna(row.get('reviews_count')) else '0'
        monthly_rev = estimate_monthly_revenue(row)
        est_rev_str = format_currency(monthly_rev)
        velocity = velocities.get(row['asin'], 0)
        lqs_score = lqs_scores[idx]
        traffic_dot = '<font color="#C62828">⬤ Ads</font>' if sponsored else '<font color="#2E7D32">⬤ Organic</font>'
        asin = str(row.get('asin', 'N/A'))
        asin_link = f'<link href="https://www.amazon.com/dp/{asin}">{asin}</link>' if asin != 'N/A' else asin

        row_data = [
            str(int(row['position'])),
            Paragraph(asin_link, ParagraphStyle('AsinCell', fontSize=7, leading=9, textColor=colors.HexColor('#0D47A1'))),
            Paragraph(truncate(brand, 16), cell_style),
            price,
            rating,
            reviews,
            est_rev_str,
            Paragraph(traffic_dot, cell_style),
        ]
        if include_lqs:
            row_data.insert(7, str(lqs_score))
        if has_velocity_data:
            row_data.append(f"{velocity:.1f}" if velocity > 0 else "0.0")
        data.append(row_data)

        if pd.notna(row.get('price')) and row.get('price') > 0:
            eff = monthly_rev / row['price']
            if eff > best_efficiency:
                best_efficiency = eff
                best_eff_row_idx = len(data) - 1

    col_widths = [0.8*cm, 2.35*cm, 2.0*cm, 1.1*cm, 0.9*cm, 1.1*cm, 1.9*cm, 1.5*cm]
    if include_lqs:
        col_widths.insert(7, 0.8*cm)
    if has_velocity_data:
        col_widths.append(0.9*cm)
    table = Table(data, colWidths=col_widths)
    style = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A4D8C')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('ALIGN', (2,1), (2,-1), 'LEFT'),
        ('ALIGN', (3,1), (6,-1), 'RIGHT'),
        ('ALIGN', (1,1), (1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 7),
        ('FONTSIZE', (0,1), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 1, colors.grey),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]
    if best_eff_row_idx is not None:
        style.append(('BACKGROUND', (0, best_eff_row_idx), (-1, best_eff_row_idx), colors.HexColor('#E8F5E9')))
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
                    data.append([
                        issue,
                        f"{pct:.0f}% of analyzed negative reviews mention this",
                        Paragraph(example, cell_style)
                    ])
                t = Table(data, colWidths=[3.5*cm, 1.8*cm, 8*cm])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A4D8C')),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                    ('GRID', (0,0), (-1,-1), 1, colors.grey),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0,0), (-1,-1), 8),
                ]))
                elements.append(t)
                elements.append(Spacer(1, 0.3*cm))
            else:
                elements.append(Paragraph("No specific complaints identified.", styles['Normal']))
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

    if 'asin' in df_amazon.columns:
        revenue_df = df_amazon.copy()
        revenue_df['est_rev'] = revenue_df.apply(estimate_monthly_revenue, axis=1)
        total_rev = revenue_df['est_rev'].sum()
        top3_rev = revenue_df.sort_values('est_rev', ascending=False).head(3)['est_rev'].sum()
        if total_rev > 0:
            recs.append(f"Revenue concentration: top 3 ASINs control {top3_rev/total_rev*100:.1f}% of total niche revenue.")

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
        recs.append(f"RED: High market concentration (CR3 = {sat_score:.1f}%). Significant barrier to entry.")
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

    if sponsored_share <= 20:
        recs.append("PPC Difficulty: <b>Low</b> (sponsored share <=20%). Paid acquisition should be manageable.")
    elif sponsored_share <= 35:
        recs.append("PPC Difficulty: <b>Medium</b>. Plan a balanced PPC + organic strategy.")
    else:
        recs.append("PPC Difficulty: <b>High</b>. Expect expensive auctions and slower profitability.")

    if 'title' in df_amazon.columns:
        leaders_text = " ".join(df_amazon.sort_values('position').head(10)['title'].dropna().astype(str).str.lower().tolist())
        candidate_gaps = {
            'black colorway': ['black'],
            'eco packaging': ['eco', 'recycl', 'sustainable'],
            '1000-piece bundle': ['1000', '1,000']
        }
        missing = [gap for gap, kws in candidate_gaps.items() if not any(k in leaders_text for k in kws)]
        if missing:
            recs.append(f"<b>Market Gaps:</b> Missing among current leaders: {', '.join(missing)}.")

    for r in recs:
        r = r.replace('sub‑niche', 'sub-niche').replace('sub■niche', 'sub-niche')
        elements.append(Paragraph(f"• {r}", styles['Normal']))
    elements.append(Spacer(1, 0.5*cm))

def create_final_summary_page(elements, sat_score, sponsored_share, avg_rating, df_amazon):
    styles = getSampleStyleSheet()
    header = ParagraphStyle('FinalSummaryHeader', parent=styles['Heading2'], fontSize=16,
                            textColor=colors.HexColor('#1A4D8C'), spaceAfter=12)
    elements.append(PageBreak())
    elements.append(Paragraph("Executive Summary", header))

    market_size = calculate_market_size(df_amazon)
    avg_price = df_amazon['price'].dropna().mean() if 'price' in df_amazon.columns else 0
    bullets = [
        f"Estimated monthly niche revenue: <b>{format_compact_currency(market_size)}</b>.",
        f"Saturation index (CR3): <b>{sat_score:.1f}%</b>.",
        f"Sponsored listings share: <b>{sponsored_share:.1f}%</b>.",
        f"Average product rating: <b>{avg_rating:.2f}</b>.",
        f"Average price level: <b>${avg_price:.2f}</b>."
    ]
    for item in bullets:
        elements.append(Paragraph(f"• {item}", styles['Normal']))
        elements.append(Spacer(1, 0.18*cm))

# ========== MAIN ==========
def generate_report(input_dir, output_file):
    global CURRENT_LOGO_PATH
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
    CURRENT_LOGO_PATH = logo_path
    df_with_rev = df_amazon.copy()
    df_with_rev['est_rev'] = df_with_rev.apply(estimate_monthly_revenue, axis=1)
    top_row = df_with_rev.sort_values('est_rev', ascending=False).head(1)
    product_image = None
    if not top_row.empty and 'image' in top_row.columns and pd.notna(top_row.iloc[0].get('image')):
        product_image = fetch_image_bytes(top_row.iloc[0].get('image'))
    elif not top_row.empty and 'images' in top_row.columns and pd.notna(top_row.iloc[0].get('images')):
        image_field = str(top_row.iloc[0].get('images'))
        url_match = re.search(r'https?://[^\s,\]"\']+', image_field)
        if url_match:
            product_image = fetch_image_bytes(url_match.group(0))

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

    display_keyword = "Nail Studs" if str(search_query).strip().lower() == "nail studs" else f"Keyword: {search_query}"
    create_title_page(elements, display_keyword, date_str, logo_path, product_image)
    create_verdict_block(elements, sat_score, avg_rating, sponsored_share, comp_reviews, final_competition)
    create_summary(elements, df_amazon, df_details, brand_map, sat_score, final_competition)

    elements.append(PageBreak())
    elements.append(Paragraph("Visual Analysis", ParagraphStyle('SectionHeader', fontSize=16,
                                                                 textColor=colors.HexColor('#1A4D8C'), spaceAfter=10)))

    sp, outliers = create_scatter_revenue(df_amazon, brand_map, max_price=20)
    if sp:
        elements.append(Image(sp, width=14*cm, height=8*cm))
        elements.append(Spacer(1, 0.5*cm))
    if outliers is not None and len(outliers) > 0:
        outlier_rows = [["ASIN", "Brand", "Price", "Est. Monthly"]]
        for _, row in outliers.head(6).iterrows():
            outlier_rows.append([
                str(row.get('asin', 'N/A')),
                truncate(brand_map.get(row.get('asin'), 'Unknown'), 14),
                f"${row.get('price', 0):.2f}",
                format_compact_currency(row.get('monthly_rev', 0))
            ])
        t = Table(outlier_rows, colWidths=[2.8*cm, 3.4*cm, 2.2*cm, 3*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#263238')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('GRID', (0,0), (-1,-1), 0.8, colors.HexColor('#90A4AE')),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('ALIGN', (2,1), (-1,-1), 'RIGHT'),
        ]))
        elements.append(Paragraph("High-Price Outliers", ParagraphStyle('OutHeader', fontSize=11, textColor=colors.HexColor('#455A64'))))
        elements.append(t)
        elements.append(Spacer(1, 0.4*cm))

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
    create_final_summary_page(elements, sat_score, sponsored_share, avg_rating, df_amazon)

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
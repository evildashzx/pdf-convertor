#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Amazon Niche Premium Report Generator
Version 17.0 – ФИНАЛЬНАЯ РАБОЧАЯ ВЕРСИЯ
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
from matplotlib.ticker import FuncFormatter

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, KeepTogether, CondPageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.utils import ImageReader

# ========== CONFIG ==========
OWNER_NAME = "Your Name or Company"
LOGO_FILE = "icon.png"
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

def normalize_asin(value):
    if pd.isna(value):
        return None
    cleaned = re.sub(r'[^A-Za-z0-9]', '', str(value).strip().upper())
    return cleaned if cleaned else None

def get_brand_for_asin(asin, brand_map, default='Unknown'):
    asin_key = normalize_asin(asin)
    if not asin_key:
        return default
    return brand_map.get(asin_key, default)

def parse_sponsored_flag(value):
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if pd.isna(value):
        return False
    if isinstance(value, (int, float)):
        return value != 0
    value_str = str(value).strip().lower()
    return value_str in {'1', 'true', 'yes', 'y', 'ads', 'sponsored'}

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

        details_brand_map = {}
        df_details = data.get('product_details')
        if df_details is not None and 'asin' in df_details.columns and 'brand' in df_details.columns:
            details_clean = df_details.dropna(subset=['asin']).drop_duplicates(subset=['asin'], keep='first')
            for _, drow in details_clean.iterrows():
                if pd.notna(drow.get('brand')):
                    asin_key = normalize_asin(drow['asin'])
                    if asin_key:
                        details_brand_map[asin_key] = normalize_brand(str(drow.get('brand')))

        data['brand_map'] = {}
        has_brand_col = 'brand' in df.columns
        for _, row in df.iterrows():
            asin = row['asin']
            asin_key = normalize_asin(asin)
            brand = details_brand_map.get(asin_key)
            if not brand or brand == 'Generic / N/A':
                if has_brand_col and pd.notna(row.get('brand')):
                    brand = normalize_brand(str(row.get('brand')))
            if not brand or brand == 'Generic / N/A':
                if pd.notna(row.get('title')):
                    fallback = extract_brand_from_title(row['title'])
                    brand = normalize_brand(fallback)
                else:
                    brand = 'Generic / N/A'
            if asin_key:
                data['brand_map'][asin_key] = brand
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
    df['asin_key'] = df['asin'].apply(normalize_asin)
    df['brand'] = df['asin_key'].map(brand_map).fillna('Unknown')
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
def create_scatter_revenue(df_amazon, brand_map, max_price=None):
    """Price vs Estimated Monthly Revenue (log scale) – возвращает BytesIO (PNG) и DataFrame выбросов"""
    if df_amazon is None or 'price' not in df_amazon.columns:
        return None, None
    df = df_amazon.copy()
    df['monthly_rev'] = df.apply(estimate_monthly_revenue, axis=1)
    df = df[df['monthly_rev'] > 0].dropna(subset=['price', 'monthly_rev'])
    if len(df) < 3:
        return None, None

    if max_price is None:
        max_price = float(df['price'].quantile(0.95))
    max_price = max(5.0, max_price)

    outliers = df[df['price'] > max_price].sort_values('price', ascending=False)
    df_plot = df[df['price'] <= max_price]
    if len(df_plot) < 3:
        return None, outliers

    fig, ax = plt.subplots(figsize=(10,6))
    scatter = ax.scatter(df_plot['price'], df_plot['monthly_rev'],
                         c=df_plot['price'], cmap='viridis', alpha=0.78,
                         edgecolors='w', linewidth=0.5, s=50)
    ax.set_yscale('log')
    ax.set_xlabel('Price ($)', fontsize=12)
    ax.set_ylabel('Monthly Revenue ($)', fontsize=12)
    ax.set_title(f'Price vs. Estimated Monthly Revenue (up to ${max_price:.2f}, 95th pct)', fontweight='bold')
    ax.grid(True, linestyle='--', alpha=0.3)
    ax.set_xlim(0, max_price * 1.02)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{int(y):,}" if y >= 1 else f"{y:g}"))

    max_price_row = df.loc[df['price'].idxmax()]
    if max_price_row['price'] <= max_price:
        ax.annotate(f"{get_brand_for_asin(max_price_row['asin'], brand_map, '?')}\n${max_price_row['price']:.2f}",
                    xy=(max_price_row['price'], max_price_row['monthly_rev']),
                    xytext=(10, -20), textcoords='offset points',
                    arrowprops=dict(arrowstyle='->', color='#263238', lw=1.2),
                    fontsize=9, color='#111111',
                    bbox=dict(boxstyle='round,pad=0.35', fc='white', ec='#0D1B2A', lw=1.2, alpha=0.92))
    else:
        y_anchor = float(df_plot['monthly_rev'].quantile(0.9))
        ax.annotate(f"Top outlier: {get_brand_for_asin(max_price_row['asin'], brand_map, '?')}\n${max_price_row['price']:.2f}",
                    xy=(max_price * 0.98, y_anchor),
                    xytext=(-10, 18), textcoords='offset points', ha='right', va='bottom',
                    fontsize=9, color='#111111',
                    bbox=dict(boxstyle='round,pad=0.35', fc='white', ec='#0D1B2A', lw=1.2, alpha=0.92))
    cbar = fig.colorbar(scatter, ax=ax, fraction=0.03, pad=0.02, aspect=30)
    cbar.set_label('Price Tier', fontsize=9)
    cbar.ax.tick_params(labelsize=8)

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
        _, current_top = ax.get_ylim()
        ax.set_ylim(0, current_top * 1.2)
    median_val = reviews.median()
    ax.axvline(median_val, color='#8B0000', linestyle='--', linewidth=2.4, label=f'Median: {median_val:.0f}', zorder=6)
    ax.set_xlabel('Number of Reviews', fontsize=11)
    ax.set_ylabel('Number of Products', fontsize=11)
    ax.set_title(f'Product Maturity Distribution (clipped at {clip_max} reviews)', fontsize=13, fontweight='bold')
    ax.grid(axis='y', linestyle='--', alpha=0.3)
    ax.legend(loc='lower right', fontsize=8, framealpha=0.85)
    if len(outliers) > 0:
        text = f"{len(outliers)} product(s) have >{clip_max} reviews:\n" + ", ".join([f"{int(r):,}" for r in outliers[:5]])
        if len(outliers) > 5:
            text += f" and {len(outliers)-5} more"
        ax.text(0.98, 0.25, text, transform=ax.transAxes, ha='right', va='bottom',
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
    hm = sns.heatmap(corr, annot=True, cmap='coolwarm', center=0, ax=ax, square=True,
                     cbar_kws={'ticks': tick_values, 'fraction': 0.02, 'aspect': 40, 'pad': 0.02})
    if hm.collections and hm.collections[0].colorbar is not None:
        hm.collections[0].colorbar.ax.tick_params(labelsize=8)
    ax.set_title('Correlation Heatmap', fontweight='bold', pad=28)
    ax.text(0.5, 1.13, 'Price vs. Rating vs. Reviews Count', transform=ax.transAxes,
            ha='center', va='bottom', fontsize=9, color='#546E7A')
    plt.tight_layout()
    img_data = io.BytesIO()
    fig.savefig(img_data, format='png', dpi=150, bbox_inches='tight')
    img_data.seek(0)
    plt.close(fig)
    return img_data

def create_price_distribution_violin(df_amazon, brand_map, top_n=6):
    if df_amazon is None or 'price' not in df_amazon.columns or 'asin' not in df_amazon.columns:
        return None
    df = df_amazon.copy()
    df['asin_key'] = df['asin'].apply(normalize_asin)
    df['brand'] = df['asin_key'].map(brand_map).fillna('Generic / N/A')
    df = df.dropna(subset=['price'])
    if df.empty:
        return None

    clip_max = float(df['price'].quantile(0.95))
    plot_xlim = clip_max * 1.02

    counts = df['brand'].value_counts()
    top_brands = counts[counts >= 2].head(top_n).index.tolist()
    if len(top_brands) < 2:
        return None

    df['brand_for_plot'] = df['brand'].apply(lambda x: x if x in top_brands else 'Other Brands')
    grouped = df.groupby('brand_for_plot')['price'].count().sort_values(ascending=False)
    plot_order = [b for b in grouped.index.tolist() if b != 'Other Brands']
    if 'Other Brands' in grouped.index:
        plot_order.append('Other Brands')

    fig, ax = plt.subplots(figsize=(12.8, 6.6))
    sns.violinplot(
        data=df,
        x='price',
        y='brand_for_plot',
        hue='brand_for_plot',
        order=plot_order,
        inner='quartile',
        cut=0,
        linewidth=1.1,
        palette='Blues',
        legend=False,
        ax=ax
    )
    sns.stripplot(
        data=df,
        x='price',
        y='brand_for_plot',
        order=plot_order,
        color='#0D47A1',
        alpha=0.35,
        size=2.8,
        jitter=0.16,
        ax=ax
    )

    ax.set_title(f'Price Distribution by Brand (Violin + Data Points, <=95th pct ${clip_max:.2f})', fontweight='bold')
    ax.set_xlabel('Price ($)')
    ax.set_ylabel('Brand')
    ax.grid(True, axis='x', linestyle='--', alpha=0.38)
    ax.set_xlim(0, max(plot_xlim, 1))

    violin_count = len(ax.collections)
    other_idx = None
    if 'Other Brands' in plot_order:
        other_idx = plot_order.index('Other Brands')
    if other_idx is not None and violin_count > 0:
        body_idx = min(other_idx, violin_count - 1)
        ax.collections[body_idx].set_alpha(0.4)
        other_prices = df.loc[df['brand_for_plot'] == 'Other Brands', 'price']
        if len(other_prices) > 0 and other_prices.max() > clip_max:
            tail_count = int((other_prices > clip_max).sum())
            ax.text(0.98, 0.05,
                    f"Other Brands tail: {tail_count} SKU(s) above 95th pct (max ${other_prices.max():.2f})",
                    transform=ax.transAxes, ha='right', va='bottom', fontsize=8.5,
                    bbox=dict(boxstyle='round', facecolor='#FFF3E0', alpha=0.85, edgecolor='#FFB74D'))

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
    elements.append(Spacer(1, 2.2*cm))
    elements.append(Paragraph("Amazon Niche Analysis", ParagraphStyle(
        'BigTitle', parent=styles['Title'], fontSize=30, textColor=colors.HexColor('#1A4D8C'),
        alignment=1, spaceAfter=12, fontName='Helvetica-Bold'
    )))
    keyword_style = ParagraphStyle(
        'KeywordFocus', parent=styles['Normal'], fontSize=26,
        textColor=colors.HexColor('#123A6F'), alignment=1, spaceAfter=18,
        fontName='Helvetica-Bold', leading=32, wordWrap='CJK', splitLongWords=True
    )
    elements.append(Spacer(1, 0.9*cm))
    keyword_block = Table(
        [[Paragraph(f"<b>{search_query}</b>", keyword_style)]],
        colWidths=[16.3*cm]
    )
    keyword_block.setStyle(TableStyle([
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    elements.append(keyword_block)

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
        visual_markup = "<para align='center'><font size='34' color='#1A4D8C'>✧</font><br/><font size='12' color='#607D8B'>Nail style icon</font></para>"
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

    elements.append(Spacer(1, 0.35*cm))
    elements.append(Paragraph("Detailed Market Landscape &amp; Entry Strategy", ParagraphStyle(
        'Subtitle', parent=styles['Normal'], fontSize=11, alignment=1, textColor=colors.HexColor('#455A64'), spaceAfter=12
    )))

    elements.append(Spacer(1, 4.6*cm))
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

def concentration_label(sat_score):
    if sat_score > 70:
        return "High Concentration"
    if sat_score > 50:
        return "Moderate Concentration"
    return "Low Concentration"

def create_summary(elements, df_amazon, df_details, brand_map, sat_score, final_competition):
    styles = getSampleStyleSheet()
    header = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontSize=16,
                            textColor=colors.HexColor('#1A4D8C'), spaceAfter=10)
    elements.append(Paragraph("Market Summary", header))

    market_size = calculate_market_size(df_amazon)
    comp_reviews, avg_reviews = competition_level_by_reviews(df_amazon)
    sponsored_share, _ = keyword_competition(df_amazon)
    concentration = concentration_color(sat_score)
    median_reviews = float(df_amazon['reviews_count'].dropna().median()) if 'reviews_count' in df_amazon.columns else 0
    concentration_note = concentration_label(sat_score)
    discrepancy_note = (
        f"Anomaly in average reviews of top 10 ({avg_reviews:,.0f}) compared to median ({median_reviews:,.0f}) "
        "indicates the presence of several dominant giant brands, creating a significant barrier for new entrants."
    )

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
        ["Saturation Index (CR3)", f"{int(sat_score)}% ({concentration_note})"],
        ["Avg. Revenue per Listing", format_compact_currency(market_size / max(1, df_amazon['asin'].nunique()))],
    ]
    if final_competition == "Very High" and 50 <= sat_score <= 70:
        data.append([
            "Competition note",
            f"*Despite a CR3 of {sat_score:.1f}%, the market is dominated by few brands with strong "
            "product differentiation and high marketing spend, making organic entry challenging.*"
        ])
    data.append(["Market structure note", discrepancy_note])
    if df_details is not None and 'is_fsa_eligible' in df_details.columns:
        fsa_pct = (df_details['is_fsa_eligible'].sum() / len(df_details)) * 100
        data.append(["FSA/HSA Eligible", f"{fsa_pct:.1f}%"])

    table = Table(data, colWidths=[5.8*cm, 10.4*cm])
    style = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A4D8C')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 1, colors.grey),
        ('TOPPADDING', (0,0), (-1,-1), 11),
        ('BOTTOMPADDING', (0,0), (-1,-1), 11),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]
    for row_idx, row in enumerate(data[1:], start=1):
        if row[0] == "Saturation Index (CR3)":
            if sat_score > 70:
                cell_bg = colors.HexColor('#FFCDD2')
                cell_fg = colors.HexColor('#B71C1C')
            elif sat_score > 50:
                cell_bg = colors.HexColor('#FFF9C4')
                cell_fg = colors.HexColor('#8D6E00')
            else:
                cell_bg = colors.HexColor('#E8F5E9')
                cell_fg = colors.HexColor('#1B5E20')
            style.extend([
                ('BACKGROUND', (0, row_idx), (1, row_idx), cell_bg),
                ('TEXTCOLOR', (0, row_idx), (1, row_idx), cell_fg),
                ('FONTNAME', (0, row_idx), (1, row_idx), 'Helvetica-Bold')
            ])
        if row[0] == "Competition (final)" and final_competition == "Very High":
            style.extend([
                ('BACKGROUND', (0, row_idx), (1, row_idx), colors.HexColor('#FFCDD2')),
                ('TEXTCOLOR', (0, row_idx), (1, row_idx), colors.HexColor('#B71C1C')),
                ('FONTNAME', (0, row_idx), (1, row_idx), 'Helvetica-Bold')
            ])
        if row[0] in ("Competition note", "Market structure note"):
            style.extend([
                ('BACKGROUND', (0, row_idx), (1, row_idx), colors.HexColor('#F5F7FA')),
                ('FONTNAME', (0, row_idx), (0, row_idx), 'Helvetica-Bold'),
                ('FONTSIZE', (0, row_idx), (1, row_idx), 9),
                ('TOPPADDING', (0, row_idx), (1, row_idx), 8),
                ('BOTTOMPADDING', (0, row_idx), (1, row_idx), 8),
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

    cell_style = ParagraphStyle('CellStyle', fontSize=8, leading=10, wordWrap='CJK')
    has_velocity_data = any(v > 0 for v in velocities.values())

    data = [["Pos", "ASIN", "Brand", "Price", "Rating", "Reviews", "Est. Rev", "SP", "Type"]]
    if has_velocity_data:
        data[0].append("Velocity")

    best_eff_row_idx = None
    best_efficiency = -1
    for rank_idx, (_, row) in enumerate(top10.iterrows(), start=1):
        brand = get_brand_for_asin(row['asin'], brand_map, 'Unknown')
        sponsored = parse_sponsored_flag(row.get('is_sponsored', False))
        price = f"${row['price']:.2f}" if pd.notna(row.get('price')) else 'N/A'
        rating = f"{row['rating']:.1f}" if pd.notna(row.get('rating')) else 'N/A'
        reviews = format_number(row['reviews_count']) if pd.notna(row.get('reviews_count')) else '0'
        monthly_rev = estimate_monthly_revenue(row)
        est_rev_str = format_currency(monthly_rev)
        velocity = velocities.get(row['asin'], 0)
        traffic_label = 'Ads' if sponsored else 'Organic'
        traffic_chip = '<font color="#C62828">Ads</font>' if sponsored else '<font color="#2E7D32">Organic</font>'
        asin = str(row.get('asin', 'N/A'))
        asin_link = f'<link href="https://www.amazon.com/dp/{asin}">{asin}</link>' if asin != 'N/A' else asin

        row_data = [
            str(rank_idx),
            Paragraph(asin_link, ParagraphStyle('AsinCell', fontSize=7, leading=9, textColor=colors.HexColor('#0D47A1'))),
            Paragraph(truncate(brand, 16), cell_style),
            price,
            rating,
            reviews,
            est_rev_str,
            traffic_label,
            Paragraph(traffic_chip, cell_style),
        ]
        if has_velocity_data:
            row_data.append(f"{velocity:.1f}" if velocity > 0 else "0.0")
        data.append(row_data)

        if pd.notna(row.get('price')) and row.get('price') > 0:
            eff = monthly_rev / row['price']
            if eff > best_efficiency:
                best_efficiency = eff
                best_eff_row_idx = len(data) - 1

    col_widths = [0.78*cm, 2.3*cm, 2.05*cm, 1.1*cm, 0.95*cm, 1.15*cm, 1.55*cm, 1.0*cm, 1.52*cm]
    if has_velocity_data:
        col_widths.append(0.95*cm)

    table = Table(data, colWidths=col_widths)
    style = [
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A4D8C')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        ('ALIGN', (2,1), (2,-1), 'LEFT'),
        ('ALIGN', (3,1), (7,-1), 'CENTER'),
        ('ALIGN', (8,1), (8,-1), 'CENTER'),
        ('ALIGN', (1,1), (1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 7.2),
        ('FONTSIZE', (0,1), (-1,-1), 7.6),
        ('GRID', (0,0), (-1,-1), 1, colors.grey),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 6.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6.5),
    ]
    if has_velocity_data:
        style.append(('ALIGN', (9,1), (9,-1), 'CENTER'))
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
        for asin, issues in list(pain_by_brand.items())[:1]:  # показываем только первого лидера
            brand = get_brand_for_asin(asin, brand_map, 'Unknown')
            elements.append(Paragraph(f"• {brand}", styles['Heading3']))
            if issues:
                data = [["Issue", "Freq", "Example"]]
                cell_style = ParagraphStyle(
                    'ExStyle',
                    fontSize=8.5,
                    leading=10,
                    wordWrap='CJK'
                )
                for issue, pct, example in issues:
                    data.append([
                        issue,
                        Paragraph(f"{pct:.0f}% of negative reviews", ParagraphStyle('FreqStyle', fontSize=7.4, leading=8.6, alignment=1)),
                        Paragraph(example, cell_style)
                    ])
                t = Table(data, colWidths=[3.2*cm, 2.6*cm, 7.5*cm])
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A4D8C')),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                    ('GRID', (0,0), (-1,-1), 1, colors.grey),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0,0), (-1,-1), 8),
                    ('TOPPADDING', (0,0), (-1,-1), 7),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 7),
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
        recs.append(f"RED: High market concentration (CR3 = {int(sat_score)}%). Significant barrier to entry.")
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
        leader_titles = df_amazon.sort_values('position').head(12)['title'].dropna().astype(str).str.lower().tolist()
        combined_titles = " ".join(leader_titles)
        generic_gap_patterns = {
            'extra large / family-size options': ['xl', 'extra large', 'family size', 'large capacity'],
            'closure convenience (zip/clip/magnetic)': ['zip', 'clip', 'closure', 'magnetic', 'double seal'],
            'travel-friendly bundles': ['travel', 'on-the-go', 'bundle', 'set of', 'multi pack'],
            'easy-clean positioning': ['dishwasher safe', 'easy clean', 'wide opening']
        }
        missing = [gap for gap, kws in generic_gap_patterns.items() if not any(k in combined_titles for k in kws)]
        if missing:
            recs.append(
                "<b>Market Gaps:</b> Potentially underrepresented in current top listings: "
                f"{', '.join(missing[:3])}. Validate using keyword checks and small PPC tests before launch."
            )

    recommendation_items = []
    for r in recs:
        r = r.replace('sub‑niche', 'sub-niche').replace('sub■niche', 'sub-niche')
        recommendation_items.append(Paragraph(f"• {r}", styles['Normal']))

    approx_lines = sum(max(1, int(np.ceil(len(re.sub(r'<[^>]+>', '', r)) / 95))) for r in recs)
    approx_height_cm = 1.2 + (approx_lines * 0.5) + (len(recs) * 0.18)
    elements.append(CondPageBreak(min(24 * cm, approx_height_cm * cm)))

    if recommendation_items:
        max_lines_per_block = 30
        chunks, current_chunk, current_lines = [], [], 0
        for idx, item in enumerate(recommendation_items):
            est_lines = max(1, int(np.ceil(len(re.sub(r'<[^>]+>', '', recs[idx])) / 95)))
            if current_chunk and (current_lines + est_lines > max_lines_per_block):
                chunks.append(current_chunk)
                current_chunk, current_lines = [], 0
            current_chunk.append(item)
            current_lines += est_lines
        if current_chunk:
            chunks.append(current_chunk)

        if chunks:
            first_block = [Paragraph("Strategic Recommendations", header)] + chunks[0]
            elements.append(KeepTogether(first_block))
            for chunk in chunks[1:]:
                elements.append(PageBreak())
                elements.append(Paragraph("Strategic Recommendations (Continued)", header))
                elements.append(KeepTogether(chunk))
    elements.append(Spacer(1, 0.5*cm))

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
    project_root = os.path.dirname(os.path.abspath(__file__))
    logo_path = os.path.join(project_root, LOGO_FILE) if os.path.exists(os.path.join(project_root, LOGO_FILE)) else None
    CURRENT_LOGO_PATH = logo_path

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

    display_keyword = str(search_query).strip() if str(search_query).strip() else "N/A"
    create_title_page(elements, display_keyword, date_str, logo_path, None)
    create_verdict_block(elements, sat_score, avg_rating, sponsored_share, comp_reviews, final_competition)
    create_summary(elements, df_amazon, df_details, brand_map, sat_score, final_competition)

    elements.append(PageBreak())
    elements.append(Paragraph("Visual Analysis", ParagraphStyle('SectionHeader', fontSize=16,
                                                                 textColor=colors.HexColor('#1A4D8C'), spaceAfter=10)))

    sp, outliers = create_scatter_revenue(df_amazon, brand_map)
    if sp:
        elements.append(Image(sp, width=14*cm, height=8*cm))
        elements.append(Spacer(1, 0.5*cm))
    if outliers is not None and len(outliers) > 0:
        outlier_rows = [["ASIN", "Brand", "Price", "Est. Monthly"]]
        for _, row in outliers.head(6).iterrows():
            outlier_rows.append([
                str(row.get('asin', 'N/A')),
                truncate(get_brand_for_asin(row.get('asin'), brand_map, 'Unknown'), 14),
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

    elements.append(PageBreak())
    elements.append(Paragraph("Correlation Heatmap &amp; Brand Price Distribution", ParagraphStyle('SectionHeader2', fontSize=15, textColor=colors.HexColor('#1A4D8C'), spaceAfter=8)))
    hm = create_heatmap(df_amazon)
    if hm:
        elements.append(Image(hm, width=12*cm, height=10*cm))
        elements.append(Spacer(1, 0.5*cm))

    bp = create_price_distribution_violin(df_amazon, brand_map)
    if bp:
        elements.append(Image(bp, width=14*cm, height=8*cm))
        elements.append(Spacer(1, 0.5*cm))

    elements.append(PageBreak())
    create_top10_table(elements, df_amazon, brand_map, velocities, min_revenue=500)

    create_advanced_review_insights(elements, df_reviews, brand_map, top_asins, pain_by_brand)

    feedback_volume = 0
    for _, issues in pain_by_brand.items():
        for _, _, example in issues:
            feedback_volume += len(str(example))
    if feedback_volume > 400:
        elements.append(PageBreak())

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
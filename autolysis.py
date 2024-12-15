# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "seaborn",
#   "pandas",
#   "matplotlib",
#   "httpx",
#   "chardet",
#   "ipykernel",
#   "openai",
#   "numpy",
#   "scipy",
# ]
# ///

import os
import sys
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import httpx
import chardet
from pathlib import Path
import asyncio
import scipy.stats as stats
import numpy as np

# Ensure UTF-8 output for compatibility
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Constants
API_URL = "https://aiproxy.sanand.workers.dev/openai/v1/chat/completions"

# Helper Functions

def get_token():
    """Retrieve API token from environment variables."""
    try:
        return os.environ["AIPROXY_TOKEN"]
    except KeyError as e:
        print(f"Error: Environment variable '{e.args[0]}' not set.")
        raise

async def load_data(file_path):
    """Load CSV data with encoding detection."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Error: File '{file_path}' not found.")

    with open(file_path, 'rb') as f:
        result = chardet.detect(f.read())
    encoding = result['encoding']
    print(f"Detected file encoding: {encoding}")
    return pd.read_csv(file_path, encoding=encoding or 'utf-8')

async def async_post_request(headers, data):
    """Make asynchronous HTTP POST requests."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(API_URL, headers=headers, json=data, timeout=30.0)
            response.raise_for_status()
            response.encoding = 'utf-8'
            return response.json()['choices'][0]['message']['content']
        except httpx.HTTPStatusError as e:
            print(f"HTTP error occurred: {e}")
            raise
        except Exception as e:
            print(f"Error during request: {e}")
            raise

async def generate_narrative(analysis, token, file_path):
    """Generate a detailed narrative based on analysis results."""
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

    prompt = (
        f"You are an experienced data analyst. Analyze the following data for the file '{file_path.name}':\n\n"
        f"Column Names: {list(analysis['summary'].keys())}\n"
        f"Summary Statistics: {analysis['summary']}\n"
        f"Missing Values: {analysis['missing_values']}\n"
        f"Correlation Matrix: {analysis['correlation']}\n"
        f"Numeric Trends: {analysis['numeric_trends']}\n"
        f"Skewness and Kurtosis: {analysis['skewness_kurtosis']}\n"
        f"Outliers: {analysis['outliers']}\n"
        f"Hypothesis Test Results (if available): {analysis.get('hypothesis_test', 'None')}\n\n"
        "Provide a detailed narrative with explicit statistical insights, "
        "explaining correlations, trends, anomalies, and outliers. Suggest further analyses if necessary."
    )

    data = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}]}
    try:
        return await async_post_request(headers, data)
    except Exception as e:
        print(f"Error during narrative generation: {e}")
        return "Narrative generation failed due to an error."
        

async def analyze_data(df, token):
    """Perform detailed data analysis and request insights from LLM."""
    if df.empty:
        raise ValueError("Error: Dataset is empty.")

    numeric_df = df.select_dtypes(include=['number'])
    categorical_df = df.select_dtypes(include=['object', 'category'])

    # Generate insights for numerical data
    summary_stats = df.describe(include='all').to_dict()
    missing_values = df.isnull().sum().to_dict()
    correlation = numeric_df.corr().to_dict() if not numeric_df.empty else {}

    # Extract specific trends for analysis
    numeric_trends = {
        column: {
            "mean": df[column].mean(),
            "std_dev": df[column].std(),
            "max": df[column].max(),
            "min": df[column].min()
        }
        for column in numeric_df.columns
    }

    # Calculate skewness and kurtosis
    skewness_kurtosis = {
        column: {
            "skewness": stats.skew(df[column].dropna()),
            "kurtosis": stats.kurtosis(df[column].dropna())
        }
        for column in numeric_df.columns
    }

    # Outlier detection
    outliers = {
        column: {
            "outliers": list(df[column][
                (df[column] > df[column].mean() + 3 * df[column].std()) |
                (df[column] < df[column].mean() - 3 * df[column].std())
            ])
        }
        for column in numeric_df.columns
    }

    # Hypothesis testing example
    hypothesis_test = {}
    if 'average_rating' in df.columns and 'num_pages' in df.columns:
        t_stat, p_value = stats.ttest_ind(df['average_rating'].dropna(), df['num_pages'].dropna())
        hypothesis_test = {'t_stat': t_stat, 'p_value': p_value}

    analysis = {
        'summary': summary_stats,
        'missing_values': missing_values,
        'correlation': correlation,
        'numeric_trends': numeric_trends,
        'skewness_kurtosis': skewness_kurtosis,
        'outliers': outliers,
        'hypothesis_test': hypothesis_test
    }

    # Request suggestions for further insights
    try:
        prompt = (
            f"Data analysis results for '{df.columns}':\n\n"
            f"Summary Statistics: {summary_stats}\n"
            f"Missing Values: {missing_values}\n"
            f"Correlation Matrix: {correlation}\n"
            f"Numeric Trends: {numeric_trends}\n"
            f"Skewness and Kurtosis: {skewness_kurtosis}\n"
            f"Outliers: {outliers}\n\n"
            "Based on these results, provide detailed insights into the dataset, "
            "highlight patterns, outliers, and possible future steps such as predictive modeling or clustering."
        )
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        data = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}]}
        suggestions = await async_post_request(headers, data)
    except Exception as e:
        suggestions = f"Error fetching suggestions: {e}"

    print("Data analysis complete.")
    return analysis, suggestions
    

async def visualize_data(df, output_dir):
    """Generate and save visualizations."""
    sns.set(style="whitegrid")
    numeric_columns = df.select_dtypes(include=['number']).columns

    # Select columns for visualization
    selected_columns = numeric_columns[:3] if len(numeric_columns) >= 3 else numeric_columns

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate visualizations (distribution plots and heatmap)
    for column in selected_columns:
        plt.figure(figsize=(8, 6))  # Adjusted figure size for better readability
        sns.histplot(df[column].dropna(), kde=True, color='cornflowerblue')  # Updated color
        plt.title(f'Distribution of {column}', fontsize=14)  # Clearer title
        plt.xlabel(column, fontsize=12)  # Added label with increased font size
        plt.ylabel('Frequency', fontsize=12)
        plt.grid(True, linestyle='--', alpha=0.7)  # Improved gridlines for clarity
        file_name = output_dir / f'{column}_distribution.png'
        plt.savefig(file_name, dpi=100)
        print(f"Saved distribution plot: {file_name}")
        plt.close()

    if len(numeric_columns) > 1:
        plt.figure(figsize=(10, 8))  # Larger heatmap size
        corr = df[numeric_columns].corr()
        sns.heatmap(
            corr, annot=True, cmap='viridis', square=True,  # Updated color palette
            cbar_kws={"shrink": 0.8}, annot_kws={"fontsize": 10}
        )
        plt.title('Correlation Heatmap', fontsize=16)  # Clearer title
        plt.xticks(fontsize=12, rotation=45)  # Adjusted font size and rotation for clarity
        plt.yticks(fontsize=12)
        file_name = output_dir / 'correlation_heatmap.png'
        plt.savefig(file_name, dpi=100)
        print(f"Saved correlation heatmap: {file_name}")
        plt.close()

async def save_narrative_with_images(narrative, output_dir):
    """Save narrative to README.md and embed image links."""
    readme_path = output_dir / 'README.md'
    image_links = "\n".join(
        [f"![{img.name}]({img.name})" for img in output_dir.glob('*.png')]
    )
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(narrative + "\n\n" + image_links)
    print(f"Narrative successfully written to {readme_path}")

async def main(file_path):
    """Main function to orchestrate the data analysis workflow."""
    print("Starting autolysis process...")

    file_path = Path(file_path)
    if not file_path.is_file():
        print(f"Error: File '{file_path}' does not exist.")
        sys.exit(1)

    try:
        token = get_token()
    except Exception as e:
        print(e)
        sys.exit(1)

    try:
        df = await load_data(file_path)
    except FileNotFoundError as e:
        print(e)
        sys.exit(1)
    print("Dataset loaded successfully.")

    print("Analyzing data...")
    try:
        analysis, suggestions = await analyze_data(df, token)
    except ValueError as e:
        print(e)
        sys.exit(1)

    print(f"LLM Analysis Suggestions: {suggestions}")

    output_dir = Path(file_path.stem)
    output_dir.mkdir(exist_ok=True)

    print("Generating visualizations...")
    await visualize_data(df, output_dir)

    print("Generating narrative using LLM...")
    narrative = await generate_narrative(analysis, token, file_path)

    if narrative != "Narrative generation failed due to an error.":
        await save_narrative_with_images(narrative, output_dir)
    else:
        print("Narrative generation failed.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py <file_path>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))

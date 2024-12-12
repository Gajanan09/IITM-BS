import sys
import os
import httpx
from sklearn.ensemble import IsolationForest
from sklearn.cluster import KMeans
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_squared_error
import numpy as np
import re
import pandas as pd
import seaborn as sns
import chardet
import matplotlib.pyplot as plt
from dateutil import parser
import subprocess
import json


# Environment variable for AI Proxy token
AIPROXY_TOKEN = os.getenv("AIPROXY_TOKEN", "eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6IjIzZjEwMDEyOTNAZHMuc3R1ZHkuaWl0bS5hYy5pbiJ9.4fR3QAcCsv_E53vfMn6AO1XHtcLS58pVx8al4ADjlPks")


# Function Definitions

def detect_file_encoding(file_path):
    """
    Detect the encoding of a CSV file.
    """
    with open(file_path, 'rb') as file:
        result = chardet.detect(file.read())
        return result['encoding']


def extract_date_using_pattern(date_str):
    """
    Parse a date string using regex to identify different date formats.
    """
    if not isinstance(date_str, str):  # Skip non-string values (e.g., NaN, float)
        return date_str  # Return the value as-is

    # Check if the string contains digits, as we expect date-like strings to contain numbers
    if not re.search(r'\d', date_str):
        return np.nan  # If no digits are found, it's not likely a date

    # Define regex patterns for common date formats
    patterns = [
        (r"\d{2}-[A-Za-z]{3}-\d{4}", "%d-%b-%Y"),   # e.g., 15-Nov-2024
        (r"\d{2}-[A-Za-z]{3}-\d{2}", "%d-%b-%y"),   # e.g., 15-Nov-24
        (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),         # e.g., 2024-11-15
        (r"\d{2}/\d{2}/\d{4}", "%m/%d/%Y"),         # e.g., 11/15/2024
        (r"\d{2}/\d{2}/\d{4}", "%d/%m/%Y"),         # e.g., 15/11/2024
    ]

    # Check which regex pattern matches the date string
    for pattern, date_format in patterns:
        if re.match(pattern, date_str):
            try:
                return pd.to_datetime(date_str, format=date_format, errors='coerce')
            except Exception as e:
                print(f"Error parsing date: {date_str} with format {date_format}. Error: {e}")
                return np.nan

    # If no regex pattern matched, try dateutil parser as a fallback
    try:
        return parser.parse(date_str, fuzzy=True, dayfirst=False)
    except Exception as e:
        print(f"Error parsing date with dateutil: {date_str}. Error: {e}")
        return np.nan


def is_likely_date_column(column):
    """
    Determines whether a column likely contains dates based on column name or content.
    """
    # Check if the column name contains date-related terms
    if isinstance(column, str):
        if any(keyword in column.lower() for keyword in ['date', 'time', 'timestamp']):
            return True

    # Check the column's content for date-like patterns (e.g., strings with numbers)
    sample_values = column.dropna().head(10)  # Check the first 10 non-NaN values
    date_patterns = [r"\d{2}-[A-Za-z]{3}-\d{2}", r"\d{2}-[A-Za-z]{3}-\d{4}", r"\d{4}-\d{2}-\d{2}", r"\d{2}/\d{2}/\d{4}"]

    for value in sample_values:
        if isinstance(value, str):
            for pattern in date_patterns:
                if re.match(pattern, value):
                    return True
    return False


def load_csv(file_path):
    """
    Read a CSV file with automatic encoding detection and flexible date parsing using regex.
    """
    try:
        print("Detecting file encoding...")
        encoding = detect_file_encoding(file_path)
        print(f"Detected encoding: {encoding}")

        # Load the CSV file with the detected encoding
        df = pd.read_csv(file_path, encoding=encoding, encoding_errors='replace')

        # Attempt to parse date columns using regex
        for column in df.columns:
            if df[column].dtype == object and is_likely_date_column(df[column]):
                # Only apply date parsing to columns likely containing dates
                print(f"Parsing dates in column: {column}")
                df[column] = df[column].apply(extract_date_using_pattern)

        return df

    except Exception as e:
        print(f"Error reading the file: {e}")
        sys.exit(1)


def analyze_data(df):
    """
    Perform a range of analysis on the dataframe.
    """
    analysis = {
        "shape": df.shape,
        "columns": df.dtypes.to_dict(),
        "missing_values": df.isnull().sum().to_dict(),
        "summary_statistics": df.describe(include="all").to_dict(),
    }
    for column in df.select_dtypes(include=[np.datetime64]).columns:
        df[column] = df[column].dt.strftime('%Y-%m-%d %H:%M:%S')
    outliers = identify_outliers(df)
    if outliers is not None:
        analysis["outliers"] = outliers.value_counts().to_dict()
    return analysis


def identify_outliers(df):
    """Detect outliers using Isolation Forest."""
    numeric_data = df.select_dtypes(include=[np.number])
    if numeric_data.empty:
        return None
    iso = IsolationForest(contamination=0.05, random_state=42)
    numeric_data["outliers"] = iso.fit_predict(numeric_data)
    return numeric_data["outliers"]


def perform_regression(df):
    """Perform regression analysis on numeric columns."""
    numeric_data = df.select_dtypes(include=[np.number])
    if numeric_data.shape[1] < 2:
        return None
    x = numeric_data.iloc[:, :-1]  # Independent variables
    y = numeric_data.iloc[:, -1]  # Dependent variable
    model = LinearRegression()
    model.fit(x, y)
    predictions = model.predict(x)
    metrics = {
        "MSE": mean_squared_error(y, predictions),
        "R2": r2_score(y, predictions),
        "Coefficients": dict(zip(x.columns, model.coef_)),
    }
    return metrics


def perform_clustering(df):
    """Perform clustering analysis on numeric columns."""
    numeric_data = df.select_dtypes(include=[np.number])
    numeric_data = numeric_data.dropna()
    if numeric_data.empty:
        return None
    kmeans = KMeans(n_clusters=3, random_state=42)
    numeric_data['Cluster'] = kmeans.fit_predict(numeric_data)
    return numeric_data['Cluster'], numeric_data.index


def summarize_correlations(df):
    """Summarize key insights from the correlation matrix."""
    numeric_data = df.select_dtypes(include=[np.number])

    if numeric_data.empty:
        return "No numeric data available to compute correlations."

    corr_matrix = numeric_data.corr()

    # Get the highest correlation pairs
    correlations = corr_matrix.unstack().sort_values(ascending=False)

    # Filter out self-correlation (corr with itself)
    correlations = correlations[correlations < 1]

    # Get the top 5 most correlated variable pairs
    top_correlations = correlations.head(5)

    summary = "Top 5 most correlated variables:\n"
    for idx, corr_value in top_correlations.items():
        summary += f"{idx[0]} & {idx[1]}: {corr_value:.2f}\n"

    return summary


def visualize_pairplot_and_clusters(df, output_folder):
    """Generate and summarize a pairplot and clustering analysis."""
    numeric_data = df.select_dtypes(include=[np.number])

    if numeric_data.empty:
        return "No numeric data available to analyze in pairplot."
    
     # Generate pairplot
    pairplot = sns.pairplot(numeric_data)
    pairplot.fig.set_size_inches(10, 8)
    
    # Save the pairplot to a file
    pairplot_file = os.path.join(output_folder, "pairplot.png")
    pairplot.savefig(pairplot_file)
    plt.close()  # Close the plot to free memory

    # Count the number of variables
    num_vars = len(numeric_data.columns)

    summary = f"A pairplot has been created with {num_vars} numeric variables.\n"

    # Describe pairwise relationships (this can be extended to specifics based on domain knowledge)
    if num_vars > 1:
        summary += "The pairplot shows the pairwise relationships between the variables, helping to identify trends, correlations, and possible outliers.\n"
    else:
        summary += "Only one numeric variable is present, so no pairwise relationships could be visualized.\n"

    return summary

def visualize_correlation_heatmap(df, output_folder):
    """Generate and save a correlation heatmap."""
    numeric_data = df.select_dtypes(include=[np.number])

    if numeric_data.empty:
        return "No numeric data available to create a heatmap."

    # Generate the correlation matrix
    corr_matrix = numeric_data.corr()

    # Create the heatmap
    plt.figure(figsize=(10, 8))
    sns.heatmap(corr_matrix, annot=True, cmap="coolwarm", fmt=".2f", linewidths=0.5)
    heatmap_file = os.path.join(output_folder, "correlation_heatmap.png")
    plt.savefig(heatmap_file)
    plt.close()

    return "Correlation heatmap saved."


def create_clustering_visualization(df, clusters, output_folder):
    """Generate clustering scatter plot visualization."""
    if clusters is None or len(clusters) == 0:
        return "No clustering results available."

    # Ensure clustering and numeric data match
    numeric_data = df.select_dtypes(include=[np.number])
    df['Cluster'] = clusters

    # Select two numeric columns for visualization
    x_col, y_col = numeric_data.columns[:2]  # Replace with your column names if needed

    plt.figure(figsize=(10, 8))
    for cluster in np.unique(clusters):
        subset = df[df["Cluster"] == cluster]
        plt.scatter(subset[x_col], subset[y_col], label=f"Cluster {cluster}")

    plt.xlabel(x_col)
    plt.ylabel(y_col)
    plt.legend()
    
    # Save the scatter plot
    clustering_file = os.path.join(output_folder, "clustering_scatter.png")
    plt.savefig(clustering_file)
    plt.close()

    return f"Clustering visualization saved at {clustering_file}"


def query_ai_insights(prompt):
    """
    Queries the AI Proxy and returns the response.
    """
    try:
        url = "https://aiproxy.sanand.workers.dev/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {AIPROXY_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "gpt-4o-mini",  # Supported chat model
            "messages": [
                {"role": "system", "content": "You are a helpful data analysis assistant. Provide insights, suggestions, and implications based on the given analysis and visualizations."},
                {"role": "user", "content": prompt},
            ],
        }
        payload_json = json.dumps(payload)
        result = subprocess.run(
            ["curl", "-X", "POST", url, "-H", f"Authorization: Bearer {AIPROXY_TOKEN}", "-H", "Content-Type: application/json", "-d", payload_json],
            capture_output=True, text=True, encoding='utf-8'
        )
        
        if result.returncode == 0 and result.stdout:
            try:
                response_data = json.loads(result.stdout)
                return response_data["choices"][0]["message"]["content"]
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error decoding response JSON: {e}")
                return "Error: Invalid response from AI Proxy."
        else:
            print(f"Error in curl request: {result.stderr}")
            return "Error: Unable to get a response from AI Proxy."
    
    except Exception as e:
        print(f"Error querying AI Proxy: {e}")
        return "Error: Unable to generate narrative."


def save_analysis_results(analysis, visualizations, story, output_folder):
    readme_path = os.path.join(output_folder, "README.md")
    with open(readme_path, "w") as f:
        f.write("# Automated Data Analysis Report\n\n")
        f.write("## Data Overview\n")
        f.write(f"**Shape**: {analysis['shape']}\n\n")
        f.write("## Summary Statistics\n")
        f.write(pd.DataFrame(analysis["summary_statistics"]).to_markdown())
        f.write("## Narrative\n")
        f.write(str(story))  # if story is a list of strings


def main():
    print("Starting script...")
    if len(sys.argv) != 2:
        print("Incorrect arguments. Usage: uv run autolysis.py dataset.csv")
        sys.exit(1)

    file_path = sys.argv[1]
    print(f"Reading file: {file_path}")
    dataset_name = os.path.splitext(os.path.basename(file_path))[0]
    output_folder = dataset_name
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    print(f"Output folder created: {output_folder}")

    df = load_csv(file_path)
    print("Dataframe loaded.")

    analysis = analyze_data(df)
    print("Analysis complete.")

    visualizations = visualize_pairplot_and_clusters(df, output_folder)
    print(f"Generated visualizations: {visualizations}")
        # Generate and save the visualizations

    visualize_pairplot_and_clusters(df, output_folder)
    print("Pairplot saved.")
    
    visualize_correlation_heatmap(df, output_folder)
    print("Correlation heatmap saved.")

    clusters, _ = perform_clustering(df)
    create_clustering_visualization(df, clusters, output_folder)
    print("Clustering scatter plot saved.")

    story = query_ai_insights(f"### Data Analysis\n{analysis}\n{visualizations}")
    print("Story created.")
    
    save_analysis_results(analysis, visualizations, story, output_folder)
    print("Results saved.")


if __name__ == "__main__":
    main()

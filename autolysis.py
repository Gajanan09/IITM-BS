# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx",
#   "pandas",
#   "numpy",
#   "seaborn",
#   "matplotlib",
#   "scikit-learn"
# ]
# ///

import os
import sys
import json
import httpx
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from typing import Dict, Any, List
import glob
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.feature_selection import mutual_info_regression
from sklearn.pipeline import Pipeline

sns.set_theme(style="whitegrid")


class AutomatedAnalysis:
    def _init_(self, csv_path: str, aiproxy_token: str):
        """
        Initialize the automated analysis class

        Args:
            csv_path (str): Path to the input CSV file
            aiproxy_token (str): AI Proxy authentication token
        """
        self.csv_path = csv_path
        self.aiproxy_token = aiproxy_token
        self.df = None
        self.analysis_results = {}
        self.output_dir = None

        # Create output directory
        # self._create_output_directory()

        # Load the CSV
        self._load_csv()

    # def _create_output_directory(self):
    #     """
    #     Create an output directory using the dataset filename
    #     """
    #     # Get the base filename without extension
    #     base_filename = os.path.splitext(os.path.basename(self.csv_path))[0]
    #
    #     # Create directory
    #     self.output_dir = os.path.join(os.getcwd(), f"{base_filename}")
    #     os.makedirs(self.output_dir, exist_ok=True)

    def _load_csv(self):
        """
        Load the CSV file and perform initial preprocessing
        """
        try:
            self.df = pd.read_csv(self.csv_path, encoding='latin-1')
            # Remove leading/trailing whitespaces from column names
            self.df.columns = self.df.columns.str.strip()
        except Exception as e:
            print(f"Error loading CSV: {e}")
            sys.exit(1)

    def _call_llm(self, messages: List[Dict[str, str]], max_tokens: int = 1000) -> str:
        """
        Call the LLM endpoint with given messages

        Args:
            messages (List[Dict]): List of message dictionaries
            max_tokens (int): Maximum tokens to generate

        Returns:
            str: LLM response
        """
        endpoint = "http://aiproxy.sanand.workers.dev/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.aiproxy_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": messages,
            "max_tokens": max_tokens
        }

        try:
            with httpx.Client() as client:
                response = client.post(endpoint, headers=headers, timeout=30, json=payload)
                print(response.json())
                response.raise_for_status()
                return response.json()['choices'][0]['message']['content']
        except Exception as e:
            print(f"LLM API call error: {e}")
            return ""

    def data_summary(self) -> Dict[str, Any]:
        """
        Generate a comprehensive data summary

        Returns:
            Dict: Summary of the dataset
        """
        summary = {
            "total_rows": len(self.df),
            "total_columns": len(self.df.columns),
            "column_types": dict(self.df.dtypes),
            "missing_values": self.df.isnull().sum().to_dict(),
            "descriptive_stats": self.df.describe().to_dict()
        }
        return summary

    def feature_importance(self) -> Dict[str, float]:
        """
        Calculate feature importance using mutual information

        Returns:
            Dict: Feature importance scores
        """
        # Prepare numeric columns
        numeric_cols = self.df.select_dtypes(include=['float64', 'int64']).columns
        new_data = self.df[numeric_cols].dropna()
        if len(new_data.columns) < 2:
            return {}

        # Assume the last column is the target variable
        X = new_data.iloc[:, :-1]
        y = new_data.iloc[:, -1]

        # Calculate mutual information
        mi_scores = mutual_info_regression(X, y)
        importance = dict(zip(X.columns, mi_scores))
        return importance

    def correlation_analysis(self) -> np.ndarray:
        """
        Perform correlation analysis

        Returns:
            np.ndarray: Correlation matrix
        """
        numeric_cols = self.df.select_dtypes(include=['float64', 'int64']).columns
        correlation_matrix = self.df[numeric_cols].corr()
        return correlation_matrix

    def cluster_analysis(self, n_clusters: int = 3) -> Dict[str, Any]:
        """
        Perform cluster analysis using K-means

        Args:
            n_clusters (int): Number of clusters to create

        Returns:
            Dict: Cluster analysis results
        """
        numeric_cols = self.df.select_dtypes(include=['float64', 'int64']).columns

        if len(numeric_cols) < 2:
            return {}

        # Standardize the features
        scaler = Pipeline([
            ('imp', SimpleImputer(missing_values=np.nan, strategy='mean')),
            ('scaler', StandardScaler()),
        ])

        X_scaled = scaler.fit_transform(self.df[numeric_cols])

        # Perform K-means clustering
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        cluster_labels = kmeans.fit_predict(X_scaled)

        return {
            "cluster_centers": kmeans.cluster_centers_,
            "cluster_labels": cluster_labels,
            "inertia": kmeans.inertia_
        }

    def create_visualizations(self):
        """
        Create multiple comprehensive visualizations based on the analysis
        """
        # 1. Main Analysis Visualization
        plt.figure(figsize=(20, 15))
        plt.subplots_adjust(hspace=0.5, wspace=0.3)

        # Correlation Heatmap
        plt.subplot(2, 2, 1)
        corr_matrix = self.correlation_analysis()
        sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', center=0,
                    square=True, linewidths=0.5, cbar_kws={"shrink": .8})
        plt.title('Correlation Heatmap', fontsize=10)
        plt.tight_layout()

        # Feature Importance Bar Plot
        plt.subplot(2, 2, 2)
        feature_imp = self.feature_importance()
        if feature_imp:
            plt.bar(feature_imp.keys(), feature_imp.values())
            plt.title('Feature Importance', fontsize=10)
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()

        # Distribution Boxplot
        plt.subplot(2, 2, 3)
        numeric_cols = self.df.select_dtypes(include=['float64', 'int64']).columns
        if len(numeric_cols) > 0:
            sns.boxplot(data=self.df[numeric_cols])
            plt.title('Distribution of Numeric Features', fontsize=10)
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()

        # PCA Variance Explained
        plt.subplot(2, 2, 4)
        if len(numeric_cols) > 1:
            pca = PCA()
            scaler = Pipeline([
                ('imp', SimpleImputer(missing_values=np.nan, strategy='mean')),
                ('scaler', StandardScaler()),
            ])
            pca.fit(scaler.fit_transform(self.df[numeric_cols]))
            plt.plot(np.cumsum(pca.explained_variance_ratio_))
            plt.title('PCA Variance Explained', fontsize=10)
            plt.xlabel('Number of Components')
            plt.ylabel('Cumulative Explained Variance')

        # Save main visualizations
        main_viz_path = os.path.join('analysis_visualizations.png')
        plt.savefig(main_viz_path, dpi=300, bbox_inches='tight')
        plt.close()

        # 2. Distribution Pairplot
        plt.figure(figsize=(15, 10))
        sns.pairplot(self.df[numeric_cols], diag_kind='kde')
        plt.suptitle('Pairwise Distribution and Relationships', y=1.02)

        # Save pairplot
        pairplot_path = os.path.join('distribution_pairplot.png')
        plt.savefig(pairplot_path, dpi=300, bbox_inches='tight')
        plt.close()

        return {
            'main_viz': main_viz_path,
            'pairplot': pairplot_path
        }

    def generate_markdown_tables(self) -> Dict[str, str]:
        """
        Generate markdown tables for different analyses

        Returns:
            Dict: Markdown formatted tables
        """
        tables = {}

        # 1. Descriptive Statistics Table
        desc_stats = self.df.describe()
        desc_table = "| Statistic | " + " | ".join(desc_stats.columns) + " |\n"
        desc_table += "|" + "|".join(["---"] * (len(desc_stats.columns) + 1)) + "|\n"
        for index, row in desc_stats.iterrows():
            desc_table += f"| {index} | " + " | ".join([f"{val:.2f}" for val in row]) + " |\n"
        tables['descriptive_stats'] = desc_table

        # 2. Feature Importance Table
        feature_imp = self.feature_importance()
        if feature_imp:
            imp_table = "| Feature | Importance |\n|---|---|\n"
            for feature, importance in sorted(feature_imp.items(), key=lambda x: x[1], reverse=True):
                imp_table += f"| {feature} | {importance:.4f} |\n"
            tables['feature_importance'] = imp_table

        # 3. Correlation Table
        corr_matrix = self.correlation_analysis()
        corr_table = "| Feature | " + " | ".join(corr_matrix.columns) + " |\n"
        corr_table += "|" + "|".join(["---"] * (len(corr_matrix.columns) + 1)) + "|\n"
        for index, row in corr_matrix.iterrows():
            corr_table += f"| {index} | " + " | ".join([f"{val:.2f}" for val in row]) + " |\n"
        tables['correlation'] = corr_table

        return tables

    def generate_narrative(self, tables: Dict[str, str], viz_paths: Dict[str, str]) -> str:
        """
        Generate a narrative markdown report

        Args:
            tables (Dict[str, str]): Markdown tables to include in the narrative
            viz_paths (Dict[str, str]): Paths to visualization files

        Returns:
            str: Markdown formatted narrative
        """
        # Prepare context for LLM
        context = f"""
        Dataset Information:
        - Total Rows: {len(self.df)}
        - Total Columns: {len(self.df.columns)}
        - Column Types: {dict(self.df.dtypes)}

        Missing Values:
        {self.df.isnull().sum()}

        Descriptive Statistics:
        {tables.get('descriptive_stats', 'No descriptive stats available')}

        Feature Importance:
        {tables.get('feature_importance', 'No feature importance available')}
        """

        # Call LLM to generate narrative
        messages = [
            {"role": "system",
             "content": "You are a data storyteller. Help create an engaging narrative about a dataset."},
            {"role": "user",
             "content": f"Create a compelling markdown story about this dataset. Include sections on data description, key insights, and potential implications. Context:\n{context}"}
        ]

        narrative = self._call_llm(messages, max_tokens=1500)

        # Append visualizations
        narrative += "\n\n## Visualizations\n\n"

        # Add main visualization
        if viz_paths.get('main_viz'):
            narrative += f"### Analysis Visualizations\n"
            narrative += f"![Analysis Visualizations](analysis_visualizations.png)\n\n"

        # Add pairplot
        if viz_paths.get('pairplot'):
            narrative += f"### Pairwise Distribution\n"
            narrative += f"![Pairwise Distribution](distribution_pairplot.png)\n\n"

        # Append tables to the narrative
        narrative += "\n## Descriptive Statistics\n\n"
        narrative += tables.get('descriptive_stats', 'No descriptive stats available')

        narrative += "\n## Feature Importance\n\n"
        narrative += tables.get('feature_importance', 'No feature importance available')

        narrative += "\n## Correlation Matrix\n\n"
        narrative += tables.get('correlation', 'No correlation data available')

        return narrative

    def run_analysis(self):
        """
        Run complete analysis workflow
        """
        # Perform analyses
        summary = self.data_summary()
        feature_imp = self.feature_importance()
        correlation = self.correlation_analysis()
        clusters = self.cluster_analysis()

        # Create visualizations
        viz_paths = self.create_visualizations()

        # Generate markdown tables
        tables = self.generate_markdown_tables()

        # Generate narrative
        narrative = self.generate_narrative(tables, viz_paths)

        # Save narrative to README.md in the output directory
        readme_path = os.path.join('README.md')
        with open(readme_path, 'w') as f:
            f.write(narrative)

        return {
            "summary": summary,
            "feature_importance": feature_imp,
            "correlation": correlation,
            "clusters": clusters
        }


def main():
    # Check if CSV file is provided
    if len(sys.argv) < 2:
        print("Usage: python autolysis.py <csv_file>")
        sys.exit(1)

    # Get CSV path and AI Proxy token
    csv_path = sys.argv[1]
    aiproxy_token = os.environ.get("AIPROXY_TOKEN")

    if not aiproxy_token:
        print("AIPROXY_TOKEN environment variable not set")
        sys.exit(1)
    # Run analysis
    if len(sys.argv) > 2:
        csv_files = glob.glob("*.csv")
        for csv_path in csv_files:
            print("Loaded CSV file:", csv_path)
            analyzer = AutomatedAnalysis(csv_path, aiproxy_token)
            analyzer.run_analysis()
    else:
        analyzer = AutomatedAnalysis(csv_path, aiproxy_token)
        analyzer.run_analysis()

    print(f"Analysis complete. Results saved to {analyzer.output_dir}")


if _name_ == "_main_":
    main()

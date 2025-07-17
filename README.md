# Grayhound

 Grayhound is an open-source PC optimization tool for removing bloatware. It leverages a Large Language Model (LLM) with Retrieval-Augmented Generation (RAG) to build an always up-to-date threat list by analyzing the latest discussions from IT communities, ensuring the most relevant protection.

## 🐺 Core Features

- AI-Driven Threat Intelligence: Instead of relying on static definitions, Grayhound uses an LLM to generate search queries and analyze web content from IT communities to find the latest bloatware.

- Dynamic DB Updates: The collected intelligence is used to build and update a local database of bloatware, complete with risk scores and reasons.

- System Scanner: Scans your PC's installed programs and running processes against the threat database.

- Clean & Report: Allows you to select and remove identified bloatware, then generates an AI-powered summary of the cleanup process.

## 🛠️ Architecture
Grayhound operates on a client-server model:

- grayhound_server: A Python-based backend that handles all core logic, including web crawling, AI analysis, database management, and system scanning commands. It communicates via WebSockets.

- grayhound-client: A Tauri-based desktop application (React + TypeScript) that provides the user interface for interacting with the server.

- Optimizer.py: A local agent that runs on the user's machine to perform system-level tasks like scanning files and terminating processes, receiving commands from the main server.

## ✅ Prerequisites
Before you begin, ensure you have the following installed:

- Anaconda or Miniconda
- Node.js (which includes npm)
- Rust and the necessary dependencies for Tauri. Follow the official Tauri setup guide for your operating system.

## 🚀 Setup and Installation

1. Clone the Repository
```
git clone https://github.com/your-username/grayhound.git
cd grayhound
```


2. Server-Side Setup (grayhound_server)
First, set up the Python environment and configure the necessary API keys.


2-a. Create Conda Environment
Navigate to the server directory and create a new Conda environment using the provided requirements file.

```
cd grayhound_server
conda create --name grayhound python=3.10 -y
conda activate grayhound
pip install -r requirements.txt
```


2-b. Configure API Keys and Database (config.ini)
You need to provide your own API keys for Google Search, Google AI, and your MongoDB connection string.

In the grayhound_server directory, rename config.ini.example to config.ini.

Open config.ini and fill in the required values.

```
[DEFAULT]
# Google Custom Search API for web crawling
# Get it from: https://developers.google.com/custom-search/v1/overview
google_api_key = YOUR_GOOGLE_API_KEY
# Get your Search Engine ID (cx) from: https://programmablesearchengine.google.com/
cx = YOUR_SEARCH_ENGINE_ID

# MongoDB Atlas connection details for storing bloatware definitions
# Get it from: https://www.mongodb.com/cloud/atlas
username = YOUR_MONGODB_USERNAME
password = YOUR_MONGODB_PASSWORD
dbname = YOUR_MONGODB_CLUSTER_NAME

[GOOGLE_AI]
# Google AI Studio API Key for LLM-based analysis
# Get it from: https://aistudio.google.com/app/apikey
API_KEY = YOUR_GOOGLE_AI_API_KEY
```

⚠️ Important: Never commit your config.ini file with your actual keys to a public repository. The .gitignore file should already be configured to prevent this.


3. Client-Side Setup (grayhound-client)
This sets up the Tauri desktop application.


3-a. Install Node.js Dependencies
Navigate to the client directory and install the required npm packages.

```
cd ../grayhound-client
npm install
```


## ▶️ Running the Application

You must start the components in the correct order for the application to function properly. Run each command in a separate terminal.

Terminal 1: Start the Local System Agent
This agent listens for commands from the main server to scan your local machine.

```
# Make sure you are in the grayhound_server directory
# and the 'grayhound' conda environment is activated
python secure_agent/Optimizer.py
```

Terminal 2: Start the Main WebSocket Server
This is the core of the application that the client connects to.

```
# Make sure you are in the grayhound_server directory
# and the 'grayhound' conda environment is activated
python Grayhound_Websocket.py
```

Terminal 3: Launch the Tauri Client
This will open the desktop application.

```
# Make sure you are in the grayhound-client directory
npm run tauri dev
```

## 📖 How to Use


1. Update Bloatware DB: The first step is to populate your database. Go to the "Update Bloatware DB" section, select your country and OS, and click "Generate Queries". Review the AI-generated queries and confirm to start the web crawling and analysis process. This may take several minutes.


2. View & Ignore DB: You can view all identified bloatware in the "View & Ignore DB" section. If there's a program you trust, you can mark it to be ignored in future scans.


3. Scan & Clean PC: Go to "Scan & Clean PC" to analyze your system. Review the list of found threats and select the ones you wish to remove. After cleaning, an AI-generated report will summarize the actions taken.


## ⚖️ Disclaimer
This tool is designed to remove unwanted software but has the potential to delete important files if used improperly. The creators are not responsible for any damage to your system. Always review the list of programs to be removed before proceeding. Proceed with caution.


## 📄 License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.


## 🤝 Contributing
Contributions are welcome! Please feel free to open an issue or submit a pull request. Consider creating a CONTRIBUTING.md file to outline the process for contributors.

CXX      = g++
CXXFLAGS = -O2 -std=c++17 -Wall -Wextra
LIBS     = -lmosquitto -lsqlite3 -lpthread
TARGET   = groundeye_orch

.PHONY: all clean

all: $(TARGET)

$(TARGET): main.cpp orchestrator.hpp logger.hpp
	$(CXX) $(CXXFLAGS) main.cpp $(LIBS) -o $(TARGET)
	@echo "Derlendi: $(TARGET)"


clean:
	rm -f $(TARGET)
